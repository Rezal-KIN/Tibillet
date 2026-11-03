"""Réutiliser les droits et cartes natifs, sans déplacer d'argent.
/ Reuse native permissions and cards without moving money.
"""
from decimal import Decimal
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django_tenants.utils import tenant_context

from seo.portal.models import (CollectiveConfiguration, GalaEdition, PrimaryCard,
                               PrimaryCardAccess, CollectiveAudit)

MANAGER_GROUP = 'Gestionnaires des Galas'
REFUND_NOTICE = 'Vous disposez de 7 jours après la date du gala pour demander le remboursement de votre solde.'


def is_manager(user):
    return bool(user.is_authenticated and user.is_active and user.espece == 'HU'
                and (user.is_superuser or user.has_perm('seo.manage_collective')))


def audit(actor, action, subject):
    CollectiveAudit.objects.create(actor=actor, action=action, subject=str(subject))


def set_venue_admin(user, venue, allowed):
    # Retirer UN lieu ne doit pas retirer le statut requis pour les autres.
    # / Removing ONE venue must not disable administration of the others.
    with transaction.atomic():
        type(user).objects.select_for_update().get(pk=user.pk)
        if allowed:
            user.client_admin.add(venue)
            user.client_achat.add(venue)
            user.groups.add(Group.objects.get_or_create(name='staff')[0])
        else:
            user.client_admin.remove(venue)
        user.is_staff = user.is_superuser or user.client_admin.exists()
        user.save(update_fields=['is_staff'])


def set_edition_enabled(edition, allowed, actor):
    from fedow_core.models import Asset
    with transaction.atomic():
        config = CollectiveConfiguration.objects.select_for_update().get(pk=1)
        edition = GalaEdition.objects.select_for_update().get(pk=edition.pk)
        if edition.enabled == allowed:
            return
        owned = Asset.objects.filter(tenant_origin=edition.venue)
        if allowed:
            owned.filter(uuid__in=edition.disabled_assets, archive=False).update(active=True)
            edition.disabled_assets = []
        else:
            edition.disabled_assets = [str(value) for value in owned.filter(active=True).values_list('uuid', flat=True)]
            owned.update(active=False)
            if config.live_venue_id == edition.venue_id:
                config.live_venue = None
                config.save(update_fields=['live_venue'])
        edition.enabled = allowed
        edition.save(update_fields=['enabled', 'disabled_assets'])
        audit(actor, 'edition_enable' if allowed else 'edition_disable', edition.venue_id)


def set_live(edition, actor):
    with transaction.atomic():
        config = CollectiveConfiguration.objects.select_for_update().get(pk=1)
        if edition is not None:
            edition = GalaEdition.objects.select_for_update().get(pk=edition.pk)
            if not edition.enabled or not edition.venue.get_primary_domain():
                raise ValidationError('Le lieu doit être activé et posséder un domaine.')
        config.live_venue = edition.venue if edition else None
        config.save(update_fields=['live_venue'])
        audit(actor, 'select_live', config.live_venue_id or 'none')


def card_allowed(card, venue):
    # Les cartes non gérées ici conservent intégralement leur fonctionnement natif.
    # / Unmanaged cards retain their native behavior.
    if not getattr(settings, 'GALA_CASHLESS_PORTAL', False):
        return True
    edition = GalaEdition.objects.filter(venue=venue).first()
    if edition is None:
        return True
    primary = PrimaryCard.objects.filter(card=card).first()
    if primary is None:
        return True
    return edition.enabled and PrimaryCardAccess.objects.filter(
        primary=primary, edition=edition, enabled=True, sync_error=False).exists()


def native_primary_matches_access(local, venue):
    if not getattr(settings, 'GALA_CASHLESS_PORTAL', False):
        return True
    access = PrimaryCardAccess.objects.filter(primary__card_id=local.carte_id, edition__venue=venue).first()
    if access is None:
        return True  # Les cartes non gérées restent natives. / Unmanaged cards stay native.
    actual = {str(value) for value in local.points_de_vente.values_list('pk', flat=True)}
    return (access.enabled and not access.sync_error and actual == set(access.point_ids)
            and local.edit_mode == access.edit_mode)


def save_card_access(primary, edition, enabled, point_ids, edit_mode, actor):
    from laboutik.models import CartePrimaire, PointDeVente
    from laboutik.carte_primaire_ancien_fedow import (
        declarer_la_carte_primaire_a_l_ancien_fedow,
        retirer_la_carte_primaire_de_l_ancien_fedow,
    )
    from fedow_connect.models import FedowConfig
    with tenant_context(edition.venue), transaction.atomic():
        # Même verrou pour autoriser et révoquer, y compris pendant l'appel Fedow.
        # / One lock for grants and revocations, including the Fedow call.
        PrimaryCard.objects.select_for_update().get(pk=primary.pk)
        points = list(PointDeVente.objects.filter(uuid__in=point_ids))
        if len(points) != len(set(point_ids)) or (enabled and not points):
            raise ValidationError('Choisissez au moins un point de vente de ce lieu.')
        access, _ = PrimaryCardAccess.objects.get_or_create(primary=primary, edition=edition)
        access.enabled = False
        access.sync_error = False
        access.save(update_fields=['enabled', 'sync_error'])
        if not enabled:
            CartePrimaire.objects.filter(carte=primary.card).delete()
        try:
            if not FedowConfig.get_solo().can_fedow():
                raise ValidationError('Lieu non relié à Fedow.')
            if enabled:
                declarer_la_carte_primaire_a_l_ancien_fedow(primary.card)
            else:
                retirer_la_carte_primaire_de_l_ancien_fedow(primary.card)
        except Exception:
            access.sync_error = True
            access.save(update_fields=['sync_error'])
            audit(actor, 'card_sync_failed', f'{primary.pk}:{edition.pk}')
            return False
        if enabled:
            local, _ = CartePrimaire.objects.update_or_create(
                carte=primary.card, defaults={'edit_mode': edit_mode})
            local.points_de_vente.set(points)
        access.enabled = enabled
        access.edit_mode = edit_mode if enabled else False
        access.point_ids = [str(point.uuid) for point in points] if enabled else []
        access.sync_error = False
        access.save()
        audit(actor, 'card_allow' if enabled else 'card_deny', f'{primary.pk}:{edition.pk}')
        return True


def balances_for(user):
    from fedow_core.services import WalletService
    if not user.wallet_id:
        return []
    editions = {row.venue_id: row for row in GalaEdition.objects.select_related('venue')}
    rows = []
    for token in WalletService.obtenir_tous_les_soldes(user.wallet):
        asset = token.asset
        edition = editions.get(asset.tenant_origin_id)
        euro = asset.currency_code == 'EUR' and asset.category in ('TLF', 'TNF', 'FED')
        rows.append({'asset': asset, 'edition': edition,
                     'amount': Decimal(token.value) / 100,
                     'unit': '€' if euro else asset.currency_code,
                     'available': asset.active and not asset.archive and (edition is None or edition.enabled),
                     'gift': asset.category == 'TNF'})
    return rows


def inventory_rows():
    """Comparer les miroirs locaux aux nombres réellement présents chez Fedow.
    / Compare local mirrors with actual Fedow counts, without importing cards.
    """
    import requests
    from django.core.cache import cache
    from django.db.models import Count
    from fedow_connect.models import FedowConfig
    from QrcodeCashless.models import Detail
    rows = []
    for edition in GalaEdition.objects.select_related('venue'):
        local = {}
        for lot in Detail.objects.filter(origine=edition.venue).annotate(count=Count('cartecashless')):
            local[lot.generation] = local.get(lot.generation, 0) + lot.count
        key = f'collective-card-inventory:{edition.venue_id}'
        remote = cache.get(key)
        if remote is None:
            try:
                with tenant_context(edition.venue):
                    config = FedowConfig.get_solo()
                    if not config.can_fedow():
                        raise ValueError('Fedow unavailable')
                    response = requests.get('https://' + config.fedow_domain() + '/collective/inventory/',
                            headers={'Authorization': 'Api-Key ' + config.get_fedow_place_admin_apikey()},
                            timeout=(3, 8), verify=not settings.DEBUG)
                    response.raise_for_status()
                    remote = response.json()
                    if not isinstance(remote, list) or any(not isinstance(row, dict) or
                            type(row.get('generation')) is not int or type(row.get('count')) is not int for row in remote):
                        raise ValueError('Invalid inventory')
                cache.set(key, remote, timeout=60)
            except (requests.RequestException, ValueError):
                remote = None
        generations = dict(local)
        if remote is not None:
            for row in remote:
                generations.setdefault(row['generation'], 0)
        if not generations:
            generations = {None: 0}
        for generation in sorted(generations, key=lambda value: value or 0):
            count = None
            if remote is not None:
                count = sum(row['count'] for row in remote if row['generation'] == generation)
            rows.append({'venue': edition.venue, 'generation': generation,
                         'local_count': local.get(generation, 0), 'remote_count': count})
    return rows


def cards_for(user, config):
    """Lire les cartes liées chez Fedow, avec le registre local en repli explicite.
    / Read linked cards from Fedow; local mirrors are an explicit fallback.
    """
    from QrcodeCashless.models import CarteCashless
    from fedow_connect.models import FedowConfig
    from fedow_connect.fedow_api import FedowAPI
    local = list(CarteCashless.objects.filter(user=user).select_related('detail'))
    if not user.wallet_id or config is None:
        return local, False
    try:
        with tenant_context(config.login_venue):
            if not FedowConfig.get_solo().can_fedow():
                return local, False
            remote = FedowAPI().NFCcard.retrieve_card_by_signature(user)
        cards = []
        for row in remote:
            cards.append({'number': row['number_printed'],
                          'detail': {'generation': row.get('origin', {}).get('generation')}})
        return cards, False
    except Exception:
        # Aucun détachement automatique en cas de panne distante.
        # / Never detach cards because a remote lookup failed.
        return local, True
