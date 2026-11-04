"""Écrans HTML du collectif ; paiements et remboursements restent natifs.
/ Collective HTML screens; payments and refunds remain native.
"""
from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.models import Group
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django_tenants.utils import tenant_context
from rest_framework import permissions, serializers, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied
from rest_framework.throttling import AnonRateThrottle

from AuthBillet.models import TibilletUser
from Customers.models import Client, Domain
from QrcodeCashless.models import CarteCashless
from seo.portal.models import (CollectiveConfiguration, GalaEdition, PrimaryCard,
                               PrimaryCardAccess, PortalTransfer)
from seo.portal.services import (MANAGER_GROUP, REFUND_NOTICE, audit, balances_for,
                                is_manager, inventory_rows, cards_for, save_card_access, set_edition_enabled,
                                set_live, set_venue_admin)

DESTINATIONS = {'account': '/my_account/', 'balance': '/my_account/balance/',
                'refund': '/my_account/', 'admin': '/admin/'}


class EditionInput(serializers.Serializer):
    gala_date = serializers.DateField(required=False, allow_null=True)


class AccessInput(serializers.Serializer):
    enabled = serializers.BooleanField(default=False)
    edit_mode = serializers.BooleanField(default=False)
    points = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)


def root_domain():
    return get_object_or_404(Domain, tenant__schema_name='public', is_primary=True).domain


def active_user(user):
    return user.is_authenticated and user.is_active and user.espece == TibilletUser.TYPE_HUM


def page(request, template, **context):
    context.update({'manager': is_manager(request.user), 'refund_notice': _(REFUND_NOTICE),
                    'page_title': _('Les Galas — Mon espace'), 'noindex_seo': True})
    return render(request, 'seo/cashless/' + template + '.html', context)


class PortalLoginThrottle(AnonRateThrottle):
    rate = '10/minute'
    scope = 'collective_login'

    def get_ident(self, request):
        from AuthBillet.utils import get_client_ip
        return get_client_ip(request) or 'unknown'


class CollectiveViewSet(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication]
    permission_classes = [permissions.AllowAny]

    def get_throttles(self):
        return [PortalLoginThrottle()] if self.action == 'begin_login' else []

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not getattr(settings, 'GALA_CASHLESS_PORTAL', False):
            raise Http404()
        if self.action not in ('login_return', 'receive') and request.tenant.schema_name != 'public':
            raise Http404()

    def handle_exception(self, exc):
        if isinstance(exc, ValidationError):
            return HttpResponseBadRequest('; '.join(exc.messages))
        if (getattr(settings, 'GALA_CASHLESS_PORTAL', False)
                and self.action in ('login_return', 'receive')
                and isinstance(exc, (PermissionDenied, Http404))):
            # Un ancien lien n'est pas une erreur d'API pour le participant.
            # / Give the participant a safe restart instead of an API error.
            response = page(self.request, 'connection_failed',
                            login_url='https://' + root_domain() + '/collectif/connexion/',
                            canonical_url='https://' + root_domain() + '/espace/')
            response.status_code = 404 if isinstance(exc, Http404) else 403
            return response
        return super().handle_exception(exc)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'no-store, private'
        # Les URL de transfert restent secrètes. Les pages contenant des
        # formulaires doivent conserver leur origine pour le contrôle CSRF.
        # / Hide transfer URLs; preserve form origins for CSRF validation.
        response['Referrer-Policy'] = ('no-referrer' if self.action in ('login_return', 'receive')
                                       else 'same-origin')
        response['X-Robots-Tag'] = 'noindex, nofollow'
        return response

    def require_manager(self, request):
        if not is_manager(request.user):
            raise PermissionDenied(_('Accès réservé aux gestionnaires du collectif.'))

    def space(self, request):
        if not active_user(request.user):
            return redirect('/collectif/connexion/')
        config = CollectiveConfiguration.objects.select_related('live_venue').filter(pk=1).first()
        cards, cards_unavailable = cards_for(request.user, config)
        operations = []
        if request.user.wallet_id:
            from fedow_core.models import Transaction
            from django.core.paginator import Paginator
            query = Transaction.objects.filter(
                Q(sender=request.user.wallet) | Q(receiver=request.user.wallet)
            ).select_related('asset', 'tenant').order_by('-datetime')
            operations = Paginator(query, 20).get_page(request.GET.get('page'))
            for operation in operations:
                operation.display_amount = Decimal(operation.amount) / 100
                operation.debit = operation.sender_id == request.user.wallet_id
        return page(request, 'account', cards=cards, cards_unavailable=cards_unavailable, balances=balances_for(request.user),
                    operations=operations, config=config)

    def begin_login(self, request):
        if active_user(request.user):
            return redirect('/espace/')
        config = CollectiveConfiguration.objects.select_related('login_venue').filter(pk=1).first()
        if config is None:
            return page(request, 'unavailable')
        domain = config.login_venue.get_primary_domain()
        if domain is None:
            raise Http404()
        # Le retour doit retrouver CE navigateur : le ticket seul ne connecte pas.
        # / The callback must find THIS browser; the ticket alone cannot sign in.
        ticket = PortalTransfer.objects.create(domain=request.get_host(), destination='root',
                         expires_at=timezone.now() + timedelta(minutes=30))
        challenges = list(request.session.get('collective_login_challenges', []))
        legacy = request.session.pop('collective_login_challenge', None)
        if legacy:
            challenges.append(legacy)
        # Une seconde tentative ne doit pas invalider le premier onglet.
        # / A second attempt must not invalidate the first tab.
        request.session['collective_login_challenges'] = challenges[-9:] + [str(ticket.pk)]
        path = '/collectif/retour/' + str(ticket.pk) + '/'
        return redirect('https://' + domain.domain + '/espace/?' + urlencode({'retour': signing.dumps(path)}))

    def login_return(self, request, ticket_id):
        if request.tenant.schema_name == 'public' or not active_user(request.user):
            raise PermissionDenied()
        config = get_object_or_404(CollectiveConfiguration, pk=1)
        if config.login_venue_id != request.tenant.pk:
            raise PermissionDenied()
        with transaction.atomic():
            ticket = get_object_or_404(PortalTransfer.objects.select_for_update(), pk=ticket_id,
                                      destination='root', user__isnull=True, used_at__isnull=True)
            if ticket.expires_at <= timezone.now() or ticket.domain != root_domain():
                raise PermissionDenied(_('Connexion expirée. Recommencez depuis votre espace.'))
            ticket.user = request.user
            ticket.expires_at = timezone.now() + timedelta(seconds=60)
            ticket.save(update_fields=['user', 'expires_at'])
        return redirect('https://' + ticket.domain + '/collectif/session/' + str(ticket.pk) + '/')

    def receive(self, request, ticket_id):
        with transaction.atomic():
            ticket = get_object_or_404(PortalTransfer.objects.select_for_update(of=('self',)).select_related('user'),
                                      pk=ticket_id, domain=request.get_host(), used_at__isnull=True)
            if ticket.expires_at <= timezone.now() or ticket.user is None or not active_user_record(ticket.user):
                raise PermissionDenied(_('Connexion expirée. Recommencez depuis votre espace.'))
            if ticket.destination == 'root':
                challenges = list(request.session.get('collective_login_challenges', []))
                legacy = request.session.get('collective_login_challenge')
                if request.tenant.schema_name != 'public' or (str(ticket.pk) not in challenges and legacy != str(ticket.pk)):
                    raise PermissionDenied()
                if str(ticket.pk) in challenges:
                    challenges.remove(str(ticket.pk))
                request.session['collective_login_challenges'] = challenges
                if legacy == str(ticket.pk):
                    request.session.pop('collective_login_challenge')
                destination = '/espace/'
            else:
                edition = get_object_or_404(GalaEdition, venue=request.tenant)
                destination = DESTINATIONS.get(ticket.destination)
                if destination is None or (not edition.enabled and ticket.destination != 'admin'):
                    raise PermissionDenied()
                if ticket.destination == 'admin' and not (ticket.user.is_superuser or ticket.user.is_tenant_admin(request.tenant)):
                    raise PermissionDenied()
            ticket.used_at = timezone.now()
            ticket.save(update_fields=['used_at'])
            login(request, ticket.user, backend='django.contrib.auth.backends.ModelBackend')
        return redirect(destination)

    def leave(self, request):
        logout(request)
        return redirect('/')

    def enter(self, request, edition_id):
        if not active_user(request.user):
            return redirect('/collectif/connexion/')
        edition = get_object_or_404(GalaEdition.objects.select_related('venue'), pk=edition_id)
        section = request.GET.get('section', 'account')
        if section not in DESTINATIONS:
            return HttpResponseBadRequest(_('Destination inconnue.'))
        if section == 'admin':
            if not (request.user.is_superuser or request.user.is_tenant_admin(edition.venue)):
                raise PermissionDenied()
        elif not edition.enabled:
            raise PermissionDenied(_('Ce lieu est désactivé.'))
        domain = edition.venue.get_primary_domain()
        if domain is None:
            raise Http404()
        ticket = PortalTransfer.objects.create(user=request.user, domain=domain.domain, destination=section,
                                               expires_at=timezone.now() + timedelta(seconds=60))
        return redirect('https://' + domain.domain + '/collectif/session/' + str(ticket.pk) + '/')

    def administration(self, request):
        if not active_user(request.user):
            return redirect('/collectif/connexion/')
        self.require_manager(request)
        config = get_object_or_404(CollectiveConfiguration, pk=1)
        return page(request, 'administration', editions=GalaEdition.objects.select_related('venue'), config=config,
                    candidates=Client.objects.exclude(categorie__in=[Client.ROOT, Client.META, Client.WAITING_CONFIG])
                                     .exclude(gala_edition__isnull=False))

    def edition(self, request, edition_id):
        self.require_manager(request)
        edition = get_object_or_404(GalaEdition.objects.select_related('venue'), pk=edition_id)
        if request.method == 'POST':
            command = request.data.get('command')
            if command == 'live':
                set_live(edition, request.user)
            elif command == 'stop_live':
                set_live(None, request.user)
            elif command in ('enable', 'disable'):
                if command == 'disable' and request.data.get('confirm') != '1':
                    return HttpResponseBadRequest(_('Confirmez la désactivation.'))
                set_edition_enabled(edition, command == 'enable', request.user)
            elif command == 'date':
                serializer = EditionInput(data={'gala_date': request.data.get('gala_date') or None})
                serializer.is_valid(raise_exception=True)
                edition.gala_date = serializer.validated_data.get('gala_date')
                edition.save(update_fields=['gala_date'])
                audit(request.user, 'edition_date', edition.pk)
            else:
                return HttpResponseBadRequest(_('Action inconnue.'))
            return redirect('/collectif/administration/')
        return page(request, 'edition', edition=edition, can_admin_venue=request.user.is_superuser or request.user.is_tenant_admin(edition.venue))

    def register_edition(self, request):
        self.require_manager(request)
        venue = get_object_or_404(Client, pk=serializers.UUIDField().run_validation(request.data.get('venue')),
                                  categorie__in=[Client.SALLE_SPECTACLE, Client.FESTIVAL])
        edition, created = GalaEdition.objects.get_or_create(venue=venue)
        if created:
            audit(request.user, 'register_edition', venue.pk)
        return redirect('/collectif/editions/' + str(edition.pk) + '/')

    def administrators(self, request):
        self.require_manager(request)
        if request.method == 'POST':
            email = serializers.EmailField().run_validation(request.data.get('email', ''))
            user = TibilletUser.objects.filter(email__iexact=email, espece=TibilletUser.TYPE_HUM).first()
            if user is None:
                messages.error(request, _('Ce compte doit d’abord se connecter à TiBillet.'))
                return redirect('/collectif/administrateurs/')
            allowed = serializers.BooleanField().run_validation(request.data.get('allowed'))
            scope = request.data.get('scope')
            with transaction.atomic():
                CollectiveConfiguration.objects.select_for_update().get(pk=1)
                if scope == 'collective':
                    group = Group.objects.get(name=MANAGER_GROUP)
                    if allowed:
                        user.groups.add(group)
                    else:
                        if group.user_set.count() <= 1 and user.groups.filter(pk=group.pk).exists():
                            raise PermissionDenied(_('Conservez au moins un gestionnaire du collectif.'))
                        user.groups.remove(group)
                else:
                    edition = get_object_or_404(GalaEdition, pk=serializers.IntegerField(min_value=1).run_validation(scope))
                    set_venue_admin(user, edition.venue, allowed)
                audit(request.user, 'grant_admin' if allowed else 'remove_admin', f'{user.pk}:{scope}')
            return redirect('/collectif/administrateurs/')
        managers = TibilletUser.objects.filter(espece=TibilletUser.TYPE_HUM, groups__name=MANAGER_GROUP)
        editions = list(GalaEdition.objects.select_related('venue').prefetch_related('venue__user_admin'))
        return page(request, 'administrators', managers=managers, editions=editions)

    def inventory(self, request):
        self.require_manager(request)
        return page(request, 'inventory', lots=inventory_rows())

    def primary_cards(self, request):
        self.require_manager(request)
        if request.method == 'POST':
            number = str(request.data.get('number', '')).strip().upper()
            card = CarteCashless.objects.filter(number__iexact=number, detail__origine__gala_edition__isnull=False).first()
            if card is None:
                messages.error(request, _('Carte absente du registre local du collectif. Importez-la avec l’administration native des cartes.'))
                return redirect('/collectif/cartes-primaires/')
            primary, created = PrimaryCard.objects.get_or_create(card=card)
            if created:
                # Préserver les autorisations existantes lors de l'ajout au registre.
                # / Preserve native access when enrolling an existing primary card.
                from laboutik.models import CartePrimaire
                for edition in GalaEdition.objects.select_related('venue'):
                    with tenant_context(edition.venue):
                        local = CartePrimaire.objects.filter(carte=card).first()
                        if local:
                            PrimaryCardAccess.objects.create(primary=primary, edition=edition, enabled=True,
                                edit_mode=local.edit_mode, point_ids=[str(value) for value in local.points_de_vente.values_list('pk', flat=True)])
                audit(request.user, 'register_primary_card', primary.pk)
            return redirect('/collectif/cartes-primaires/' + str(primary.pk) + '/')
        return page(request, 'primary_cards', cards=PrimaryCard.objects.select_related('card'))

    def primary_card(self, request, primary_id):
        self.require_manager(request)
        primary = get_object_or_404(PrimaryCard.objects.select_related('card'), pk=primary_id)
        if request.method == 'POST':
            edition = get_object_or_404(GalaEdition, pk=serializers.IntegerField(min_value=1).run_validation(request.data.get('edition')))
            serializer = AccessInput(data={'enabled': request.data.get('enabled', False),
                         'edit_mode': request.data.get('edit_mode', False), 'points': request.data.getlist('points') if hasattr(request.data, 'getlist') else request.data.get('points', [])})
            serializer.is_valid(raise_exception=True)
            values = serializer.validated_data
            try:
                success = save_card_access(primary, edition, values['enabled'],
                                  [str(value) for value in values['points']], values['edit_mode'], request.user)
            except ValidationError as error:
                messages.error(request, '; '.join(error.messages))
            else:
                if not success:
                    messages.error(request, _('Fedow n’a pas confirmé l’autorisation. Accès refusé ; vous pouvez réessayer.'))
            return redirect('/collectif/cartes-primaires/' + str(primary.pk) + '/')
        from laboutik.models import PointDeVente
        rows = []
        for edition in GalaEdition.objects.select_related('venue'):
            access = PrimaryCardAccess.objects.filter(primary=primary, edition=edition).first()
            with tenant_context(edition.venue):
                points = list(PointDeVente.objects.order_by('name'))
            rows.append({'edition': edition, 'access': access, 'points': points})
        return page(request, 'primary_card', primary=primary, rows=rows)


def active_user_record(user):
    return user.is_active and user.email_valid and user.espece == TibilletUser.TYPE_HUM
