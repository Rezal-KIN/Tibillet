"""Isolation, droits et passage de session ; aucun envoi ni remboursement réel.
/ Isolation, permissions and session handoff; no real emails or refunds.
"""
from datetime import timedelta
from urllib.parse import urlsplit, parse_qs
from django.core import signing
from unittest.mock import patch
from types import SimpleNamespace
from uuid import uuid4

from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import RequestFactory, override_settings
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import tenant_context, schema_context
from rest_framework.test import force_authenticate

from AuthBillet.models import TibilletUser, Wallet
from Customers.models import Client, Domain
from QrcodeCashless.models import CarteCashless
from fedow_core.models import Asset, Token, Federation, Transaction
from laboutik.models import CartePrimaire, PointDeVente
from seo.portal.models import (CollectiveConfiguration, GalaEdition, PrimaryCard,
                               PrimaryCardAccess, PortalTransfer)
from seo.portal.services import (balances_for, card_allowed, inventory_rows, is_manager, native_primary_matches_access, save_card_access,
                                set_edition_enabled, set_live, set_venue_admin)
from seo.portal.views import CollectiveViewSet


class CollectiveTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = 'Gala 2026 isolated'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with schema_context('public'):
            cls.other = Client(schema_name='collective_other', name='Gala 2027 isolated')
            cls.other.save(verbosity=0)
            Domain.objects.create(tenant=cls.other, domain='other.test', is_primary=True)

    @classmethod
    def tearDownClass(cls):
        connection.set_schema_to_public()
        # Le runner supprime la base de test entière ; le collecteur Django ne
        # sait pas supprimer un tenant depuis public (tables métier absentes).
        # / The runner drops the isolated test database, including both schemas.
        cls.remove_allowed_test_domain()

    def setUp(self):
        self.enterContext(override_settings(GALA_CASHLESS_PORTAL=True, SOLO_CACHE=None,
                                           ALLOWED_HOSTS=['portal.test', 'other.test', self.domain.domain]))
        self.enterContext(patch('celery.app.task.Task.apply_async'))
        connection.set_tenant(self.tenant)
        self.root = Client(schema_name='public', name='Collective isolated')
        self.root.auto_create_schema = False
        with schema_context('public'):
            self.root.save()
            Domain.objects.create(tenant=self.root, domain='portal.test', is_primary=True)
        self.edition = GalaEdition.objects.create(venue=self.tenant, gala_date=timezone.now().date())
        self.second = GalaEdition.objects.create(venue=self.other)
        self.config = CollectiveConfiguration.objects.create(login_venue=self.tenant, live_venue=self.tenant)
        self.user = TibilletUser.objects.create(username=uuid4().hex, email=uuid4().hex+'@example.test',
                                               is_active=True, email_valid=True)
        self.wallet = Wallet.objects.create(name='isolated user')
        self.user.wallet = self.wallet
        self.user.save(update_fields=['wallet'])
        self.owner = Wallet.objects.create(name='isolated venue')
        self.asset = Asset.objects.create(name='Gala 2026', category='TLF', currency_code='EUR',
                                         wallet_origin=self.owner, tenant_origin=self.tenant, active=True)
        Token.objects.create(wallet=self.wallet, asset=self.asset, value=1250)
        self.manager = TibilletUser.objects.create(username=uuid4().hex, email=uuid4().hex+'@example.test',
                                                  is_active=True, email_valid=True)
        permission = Permission.objects.get(content_type__app_label='seo', codename='manage_collective')
        self.manager.user_permissions.add(permission)
        self.card = CarteCashless.objects.create(tag_id=uuid4().hex[:8].upper(), number=uuid4().hex[:8].upper(), user=self.user)
        self.primary = PrimaryCard.objects.create(card=self.card)
        self.point = PointDeVente.objects.create(name='Bar isolated')

    def request(self, path, method='get', data=None, user=None, tenant=None):
        request = getattr(RequestFactory(), method)(path, data=data or {}, HTTP_HOST='portal.test', secure=True)
        request.tenant = tenant or self.root
        request.user = user or AnonymousUser()
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        MessageMiddleware(lambda r: None).process_request(request)
        if user:
            force_authenticate(request, user=user)
        return request

    def view(self, action, request, **kwargs):
        return CollectiveViewSet.as_view({request.method.lower(): action})(request, **kwargs)

    def test_native_login_roundtrip_keeps_the_original_root_browser(self):
        root_request = self.request('/collectif/connexion/')
        response = self.view('begin_login', root_request)
        target = urlsplit(response.url)
        self.assertEqual(target.hostname, self.domain.domain)
        callback_path = signing.loads(parse_qs(target.query)['retour'][0])
        ticket_id = root_request.session['collective_login_challenges'][-1]
        from seo.cashless_portal import portal_space
        tenant_request = self.request(target.path+'?'+target.query, user=self.user, tenant=self.tenant)
        self.assertEqual(portal_space(tenant_request).url, callback_path)
        returned = self.view('login_return', tenant_request, ticket_id=ticket_id)
        self.assertEqual(urlsplit(returned.url).hostname, 'portal.test')
        receive = self.request('/collectif/session/')
        receive.session = root_request.session
        self.assertEqual(self.view('receive', receive, ticket_id=ticket_id).url, '/espace/')

    def test_inventory_queries_only_registered_venue_and_handles_fedow_failure(self):
        from django.core.cache import cache
        for edition in (self.edition, self.second):
            cache.delete(f'collective-card-inventory:{edition.venue_id}')
        with patch('fedow_connect.models.FedowConfig.get_solo') as config, patch('requests.get') as read:
            config.return_value.can_fedow.return_value = True
            config.return_value.fedow_domain.return_value = 'fedow.test'
            config.return_value.get_fedow_place_admin_apikey.return_value = 'isolated-key'
            read.return_value.json.return_value = [{'generation': 1, 'count': 42, 'linked_count': 3}]
            rows = inventory_rows()
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row['remote_count'] == 42 for row in rows))
            self.assertEqual(read.call_count, 2)
        for edition in (self.edition, self.second):
            cache.delete(f'collective-card-inventory:{edition.venue_id}')
        with patch('fedow_connect.models.FedowConfig.get_solo') as config:
            config.return_value.can_fedow.return_value = False
            self.assertTrue(all(row['remote_count'] is None for row in inventory_rows()))

    def test_participant_cannot_manage_collective(self):
        response = self.view('administration', self.request('/collectif/administration/', user=self.user))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(is_manager(self.user))
        self.assertTrue(is_manager(self.manager))

    def test_account_uses_only_own_wallet_and_includes_refund_notice(self):
        other_wallet = Wallet.objects.create(name='private other user')
        Token.objects.create(wallet=other_wallet, asset=self.asset, value=987654)
        rows = balances_for(self.user)
        self.assertEqual(len(rows), 1)
        self.assertEqual(str(rows[0]['amount']), '12.5')
        response = self.view('space', self.request('/espace/', user=self.user))
        self.assertContains(response, '7 jours après la date du gala')
        self.assertContains(response, '12,50')
        self.assertNotContains(response, '9876')
        self.assertContains(response, 'Gala 2026 isolated')

    def test_shared_asset_is_not_counted_twice_and_gift_remains_separate(self):
        self.asset.federated_with.add(self.other)
        gift = Asset.objects.create(name='Cadeau', category='TNF', currency_code='EUR', wallet_origin=self.owner,
                                    tenant_origin=self.other, active=True)
        Token.objects.create(wallet=self.wallet, asset=gift, value=200)
        rows = balances_for(self.user)
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(row['gift'] for row in rows), 1)

    def test_disable_is_manual_and_keeps_tokens_and_history(self):
        set_edition_enabled(self.edition, False, self.manager)
        self.asset.refresh_from_db()
        self.config.refresh_from_db()
        self.assertFalse(self.asset.active)
        self.assertIsNone(self.config.live_venue_id)
        self.assertEqual(Token.objects.get(wallet=self.wallet, asset=self.asset).value, 1250)
        self.assertEqual(len(balances_for(self.user)), 1)
        set_edition_enabled(self.edition, True, self.manager)
        self.asset.refresh_from_db()
        self.assertTrue(self.asset.active)

    def test_live_selection_never_selects_disabled_edition(self):
        self.second.enabled = False
        self.second.save()
        with self.assertRaises(ValidationError):
            set_live(self.second, self.manager)
        set_live(None, self.manager)
        self.config.refresh_from_db()
        self.assertIsNone(self.config.live_venue_id)

    def test_removing_one_venue_admin_keeps_other_venue_rights(self):
        set_venue_admin(self.user, self.tenant, True)
        set_venue_admin(self.user, self.other, True)
        set_venue_admin(self.user, self.tenant, False)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_staff)
        self.assertTrue(self.user.is_tenant_admin(self.other))
        self.assertFalse(self.user.is_tenant_admin(self.tenant))

    def test_native_card_access_is_default_deny_for_new_edition(self):
        self.assertFalse(card_allowed(self.card, self.other))
        PrimaryCardAccess.objects.create(primary=self.primary, edition=self.edition, enabled=True)
        self.assertTrue(card_allowed(self.card, self.tenant))
        self.assertFalse(card_allowed(self.card, self.other))
        with patch('laboutik.carte_primaire_ancien_fedow.retirer_la_carte_primaire_de_l_ancien_fedow'), \
             patch('fedow_connect.models.FedowConfig.get_solo') as fedow:
            fedow.return_value.can_fedow.return_value = True
            save_card_access(self.primary, self.edition, False, [], False, self.manager)
        self.assertFalse(card_allowed(self.card, self.tenant))

    def test_card_grant_reuses_native_pos_and_rejects_other_venue_points(self):
        with patch('laboutik.carte_primaire_ancien_fedow.declarer_la_carte_primaire_a_l_ancien_fedow'), \
             patch('fedow_connect.models.FedowConfig.get_solo') as fedow:
            fedow.return_value.can_fedow.return_value = True
            self.assertTrue(save_card_access(self.primary, self.edition, True, [str(self.point.pk)], False, self.manager))
        native = CartePrimaire.objects.get(carte=self.card)
        self.assertEqual(list(native.points_de_vente.all()), [self.point])
        self.assertTrue(native_primary_matches_access(native, self.tenant))
        native.edit_mode = True
        native.save(update_fields=['edit_mode'])
        self.assertFalse(native_primary_matches_access(native, self.tenant))
        with self.assertRaises(ValidationError):
            save_card_access(self.primary, self.second, True, [str(self.point.pk)], False, self.manager)

    def test_failed_fedow_grant_never_authorizes_card(self):
        with patch('fedow_connect.models.FedowConfig.get_solo') as fedow:
            fedow.return_value.can_fedow.return_value = False
            self.assertFalse(save_card_access(self.primary, self.edition, True, [str(self.point.pk)], False, self.manager))
        self.assertFalse(card_allowed(self.card, self.tenant))
        self.assertFalse(CartePrimaire.objects.filter(carte=self.card).exists())

    def test_session_ticket_is_bound_to_domain_and_consumed_once(self):
        ticket = PortalTransfer.objects.create(user=self.user, domain='other.test', destination='account',
                                               expires_at=timezone.now()+timedelta(seconds=60))
        wrong = self.view('receive', self.request('/collectif/session/', tenant=self.other), ticket_id=ticket.pk)
        self.assertEqual(wrong.status_code, 404)
        request = self.request('/collectif/session/', tenant=self.other)
        request.META['HTTP_HOST'] = 'other.test'
        response = self.view('receive', request, ticket_id=ticket.pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/my_account/')
        replay = self.view('receive', request, ticket_id=ticket.pk)
        self.assertEqual(replay.status_code, 404)

    def test_login_return_requires_initial_browser(self):
        ticket = PortalTransfer.objects.create(user=self.user, domain='portal.test', destination='root',
                                               expires_at=timezone.now()+timedelta(seconds=60))
        request = self.request('/collectif/session/')
        denied = self.view('receive', request, ticket_id=ticket.pk)
        self.assertEqual(denied.status_code, 403)
        self.assertContains(denied, 'Reprendre la connexion', status_code=403)
        self.assertNotContains(denied, str(ticket.pk), status_code=403)
        request.session['collective_login_challenge'] = str(ticket.pk)
        response = self.view('receive', request, ticket_id=ticket.pk)
        self.assertEqual(response.url, '/espace/')

    def test_expired_ticket_and_admin_escalation_are_refused(self):
        for destination, expires in [('admin', timezone.now()+timedelta(seconds=30)),
                                     ('account', timezone.now()-timedelta(seconds=1))]:
            ticket = PortalTransfer.objects.create(user=self.user, domain='other.test', destination=destination, expires_at=expires)
            request = self.request('/collectif/session/', tenant=self.other)
            request.META['HTTP_HOST'] = 'other.test'
            self.assertEqual(self.view('receive', request, ticket_id=ticket.pk).status_code, 403)

    def test_get_cannot_change_edition_and_post_requires_confirmation(self):
        request = self.request('/collectif/editions/', user=self.manager)
        self.assertEqual(self.view('edition', request, edition_id=self.edition.pk).status_code, 200)
        self.edition.refresh_from_db()
        self.assertTrue(self.edition.enabled)
        request = self.request('/collectif/editions/', method='post', data={'command':'disable'}, user=self.manager)
        self.assertEqual(self.view('edition', request, edition_id=self.edition.pk).status_code, 400)

    def test_real_http_rejects_csrf_and_checks_permissions(self):
        from django.test import Client as HttpClient
        client = HttpClient(enforce_csrf_checks=True)
        client.force_login(self.manager)
        response = client.post('/collectif/editions/'+str(self.edition.pk)+'/',
                               {'command': 'disable', 'confirm': '1'}, HTTP_HOST='portal.test', secure=True)
        self.assertEqual(response.status_code, 403)
        self.edition.refresh_from_db()
        self.assertTrue(self.edition.enabled)
        response = client.get('/espace/', HTTP_HOST='portal.test', secure=True)
        self.assertEqual(response.status_code, 200)

    def test_two_login_tabs_keep_the_first_browser_challenge(self):
        from django.test import Client as HttpClient
        browser = HttpClient()
        callbacks = []
        for _ in range(2):
            response = browser.get('/collectif/connexion/', HTTP_HOST='portal.test', secure=True)
            callbacks.append(signing.loads(parse_qs(urlsplit(response.url).query)['retour'][0]))
        # Deux onglets, deux retours valides dans le même navigateur.
        # / Both tabs must remain valid in the initiating browser.
        venue_browser = HttpClient()
        venue_browser.force_login(self.user)
        for callback in callbacks:
            response = venue_browser.get(callback, HTTP_HOST=self.domain.domain, secure=True)
            self.assertEqual(response.status_code, 302)
            response = browser.get(urlsplit(response.url).path, HTTP_HOST='portal.test', secure=True)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, '/espace/')

    def test_portal_form_policy_allows_csrf_protected_logout(self):
        from django.test import Client as HttpClient
        browser = HttpClient(enforce_csrf_checks=True)
        browser.force_login(self.user)
        response = browser.get('/espace/', HTTP_HOST='portal.test', secure=True)
        # no-referrer transforme l'Origin des formulaires en null dans Chromium.
        # / no-referrer makes native form submissions send Origin: null.
        self.assertEqual(response['Referrer-Policy'], 'same-origin')
        token = browser.cookies['csrftoken'].value
        denied = browser.post('/collectif/deconnexion/', {'csrfmiddlewaretoken': token},
                              HTTP_HOST='portal.test', HTTP_ORIGIN='null', secure=True)
        self.assertEqual(denied.status_code, 403)
        response = browser.post('/collectif/deconnexion/', {'csrfmiddlewaretoken': token},
                                HTTP_HOST='portal.test', HTTP_ORIGIN='https://portal.test', secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('_auth_user_id', browser.session)

    def test_admin_templates_render_and_malformed_role_is_rejected(self):
        for action in ['administration', 'administrators', 'inventory', 'primary_cards']:
            response = self.view(action, self.request('/collectif/', user=self.manager))
            self.assertEqual(response.status_code, 200, action)
        response = self.view('primary_card', self.request('/collectif/', user=self.manager), primary_id=self.primary.pk)
        self.assertEqual(response.status_code, 200)
        response = self.view('administrators', self.request('/collectif/', method='post', user=self.manager,
            data={'email': self.user.email, 'scope': str(self.edition.pk), 'allowed': 'invalid'}))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.user.client_admin.exists())

    def prepare_native_creation(self):
        # Seul un emplacement de la base de test est consommé.
        # / Consume only a slot from the isolated test database.
        with schema_context('public'):
            self.second.delete()
            self.other.refresh_from_db()
            self.other.categorie = Client.WAITING_CONFIG
            self.other.save()
        return SimpleNamespace(tenant=None, organisation='Edition '+uuid4().hex,
                               email=self.user.email, slug='edition-'+uuid4().hex,
                               dns_choice='test', site_web='', short_description='',
                               save=lambda: None)

    def create_native_venue(self, draft, wallet_ready=True):
        from BaseBillet.validators import TenantCreateValidator
        wallet = Wallet.objects.filter(origin=self.other).first()
        if wallet is None and wallet_ready:
            wallet = Wallet.objects.create(origin=self.other, name='Portefeuille du nouveau lieu')
        with patch('BaseBillet.validators.schema_est_entierement_migre', return_value=True), \
             patch('BaseBillet.validators.get_or_create_user', return_value=self.user), \
             patch('BaseBillet.validators.RootConfiguration.get_solo', side_effect=Exception('Stripe absent du test')), \
             patch('fedow_connect.fedow_api.FedowAPI'), \
             patch('fedow_connect.models.FedowConfig.get_solo') as fedow:
            fedow.return_value.can_fedow.return_value = True
            fedow.return_value.wallet = wallet if wallet_ready else None
            return TenantCreateValidator.create_tenant(draft)

    def test_native_creation_applies_gala_settings_once_and_preserves_existing_venue(self):
        from django.conf import settings
        from BaseBillet.models import Configuration
        from BaseBillet.validators import TenantCreateValidator
        draft = self.prepare_native_creation()
        with tenant_context(self.tenant):
            existing = Configuration.get_solo()
            before = {f.name:getattr(existing, f.name) for f in existing._meta.fields if f.name.startswith('module_')}
        with tenant_context(self.other):
            prepared = Configuration.get_solo()
            prepared.module_pages = True
            prepared.module_booking = True
            prepared.module_caisse = False
            prepared.save()

        venue = self.create_native_venue(draft)
        self.assertEqual(venue.pk, self.other.pk)
        edition = GalaEdition.objects.get(venue=venue)
        self.assertTrue(edition.currency_isolated)
        self.assertNotEqual(edition.currency_id, self.asset.pk)
        self.assertEqual(edition.currency.tenant_origin_id, venue.pk)
        self.assertEqual(Asset.objects.filter(tenant_origin=venue).count(), 1)
        with tenant_context(venue):
            from BaseBillet.models import Product
            from kiosk.credit import trouver_le_produit_de_recharge_de_la_borne
            product, free_price = trouver_le_produit_de_recharge_de_la_borne()
            self.assertEqual(product.asset_id, edition.currency_id)
            self.assertIsNotNone(free_price)
            self.assertEqual(product.prices.count(), 4)
            self.assertEqual(Product.objects.filter(asset=edition.currency).count(), 1)
            config = Configuration.get_solo()
            self.assertEqual(set(settings.GALA_NEW_VENUE_MODULES), set(before))
            for field, value in settings.GALA_NEW_VENUE_MODULES.items():
                self.assertEqual(getattr(config, field), value, field)
            self.assertTrue(config.module_federation)
            self.assertTrue(config.module_monnaie_locale)
            self.assertTrue(config.module_caisse)
            self.assertFalse(config.module_pages)
            point = PointDeVente.objects.create(name='Bar de la nouvelle edition')
            self.assertTrue(point.service_direct)
            self.assertFalse(point.accepte_commandes)
            config.module_booking = True
            config.save()
        with self.assertRaisesRegex(Exception, 'Tenant already exists'):
            TenantCreateValidator.create_tenant(draft)
        with tenant_context(venue):
            self.assertTrue(Configuration.get_solo().module_booking)
            self.assertEqual(Asset.objects.filter(tenant_origin=venue).count(), 1)
        with tenant_context(self.tenant):
            current = Configuration.get_solo()
            self.assertEqual({name:getattr(current, name) for name in before}, before)

    @override_settings(GALA_CASHLESS_PORTAL=False)
    def test_native_creation_outside_gala_preserves_native_configuration(self):
        from BaseBillet.models import Configuration
        draft = self.prepare_native_creation()
        with tenant_context(self.other):
            config = Configuration.get_solo()
            config.module_pages = True
            config.module_caisse = False
            config.save()
        venue = self.create_native_venue(draft)
        with tenant_context(venue):
            config = Configuration.get_solo()
            self.assertTrue(config.module_pages)
            self.assertFalse(config.module_caisse)
            self.assertFalse(Asset.objects.filter(tenant_origin=venue).exists())
            self.assertFalse(GalaEdition.objects.filter(venue=venue).exists())

    def test_native_gala_creation_does_not_consume_legacy_slot(self):
        draft = self.prepare_native_creation()
        with schema_context('public'):
            self.other.moteur_monnaie = Client.MOTEUR_LEGACY
            self.other.save()
        with self.assertRaisesRegex(Exception, 'No waiting tenant'):
            self.create_native_venue(draft)
        with schema_context('public'):
            self.other.refresh_from_db()
        self.assertEqual(self.other.categorie, Client.WAITING_CONFIG)
        self.assertIsNone(draft.tenant)

    def isolate_two_editions(self):
        self.edition.currency_isolated = True
        self.edition.currency = self.asset
        self.edition.save()
        with tenant_context(self.other):
            other_wallet = Wallet.objects.create(origin=self.other, name='Emetteur B')
            currency = Asset.objects.create(name='Monnaie B', category=Asset.TLF, currency_code='EUR',
                                            tenant_origin=self.other, wallet_origin=other_wallet)
        self.second.currency_isolated = True
        self.second.currency = currency
        self.second.save()
        return currency

    def test_currency_initialization_resumes_without_resetting_settings_or_duplicating_currency(self):
        from BaseBillet.models import Configuration
        from fedow_core.services import AssetService
        draft = self.prepare_native_creation()
        with self.assertRaises(ValidationError):
            self.create_native_venue(draft, wallet_ready=False)
        edition = GalaEdition.objects.get(venue=draft.tenant)
        self.assertTrue(edition.currency_isolated)
        self.assertIsNone(edition.currency_id)
        self.assertFalse(AssetService.obtenir_assets_accessibles(draft.tenant).exists())
        with self.assertRaises(ValidationError):
            set_live(edition, self.manager)
        with tenant_context(draft.tenant):
            config = Configuration.get_solo()
            config.module_booking = True
            config.save()
        self.create_native_venue(draft)
        with tenant_context(draft.tenant):
            self.assertTrue(Configuration.get_solo().module_booking)
            self.assertEqual(Asset.objects.filter(tenant_origin=draft.tenant).count(), 1)
        edition.refresh_from_db()
        with patch('fedow_connect.models.FedowConfig.get_solo'):
            self.assertEqual(edition.prepare_currency().pk, edition.currency_id)

    def test_failed_native_profile_does_not_leave_a_partially_initialized_edition(self):
        draft = self.prepare_native_creation()
        with patch('BaseBillet.models.Configuration.get_solo', side_effect=RuntimeError('Profil indisponible')):
            with self.assertRaises(RuntimeError):
                self.create_native_venue(draft)
        self.other.refresh_from_db()
        self.assertEqual(self.other.categorie, Client.WAITING_CONFIG)
        self.assertFalse(GalaEdition.objects.filter(venue=self.other).exists())
        self.assertFalse(Asset.objects.filter(tenant_origin=self.other).exists())

    def test_two_active_galas_reject_shared_foreign_currency_before_any_money_moves(self):
        from fedow_core.services import AssetService, TransactionService, WalletService
        currency_b = self.isolate_two_editions()
        federation = Federation.objects.create(name='Partage explicite test', created_by=self.tenant)
        federation.tenants.add(self.tenant, self.other)
        federation.assets.add(self.asset)
        self.assertEqual(list(AssetService.obtenir_assets_accessibles(self.other)), [currency_b])
        from laboutik.views import _soldes_de_la_cascade_fiduciaire
        self.assertEqual(_soldes_de_la_cascade_fiduciaire(
            self.wallet, AssetService.obtenir_assets_accessibles(self.other)), {})
        before = Transaction.objects.count()
        for action in (Transaction.SALE, Transaction.REFILL, Transaction.REFUND):
            with self.assertRaises(ValidationError):
                TransactionService.creer(sender=self.wallet, receiver=currency_b.wallet_origin, asset=self.asset,
                                        montant_en_centimes=100, tenant=self.other, action=action)
        self.assertEqual(Transaction.objects.count(), before)
        self.assertEqual(WalletService.obtenir_solde(self.wallet, self.asset), 1250)
        self.assertEqual(WalletService.obtenir_solde(self.wallet, currency_b), 0)
        self.assertTrue(self.edition.enabled and self.second.enabled)

    def test_isolated_gala_does_not_debit_or_refund_other_fedow_balances(self):
        from laboutik.views import (lire_depensable_fed_frais, _debiter_legacy,
                                   _vider_la_carte_sur_l_ancien_fedow, _lire_la_carte_sur_l_ancien_fedow)
        currency_b = self.isolate_two_editions()
        with tenant_context(self.other), patch('laboutik.views.FedowAPI') as api:
            api.return_value.NFCcard.retrieve.return_value = {'wallet': {'tokens': [
                {'asset_category': 'FED', 'value': 100000, 'asset': {'uuid': str(uuid4())}}]}}
            self.assertEqual(lire_depensable_fed_frais(self.card), (0, True))
            with self.assertRaises(ValidationError):
                _debiter_legacy(self.card, 'PRIMARY', 100, uuid4())
            self.assertIsNone(_vider_la_carte_sur_l_ancien_fedow(self.card, 'PRIMARY', False))
            self.assertEqual(_lire_la_carte_sur_l_ancien_fedow(self.card).jetons, [])
            api.assert_not_called()

    def paid_topup(self, currency, venue, amount):
        from decimal import Decimal
        from ApiBillet.serializers import get_or_create_price_sold
        from BaseBillet.models import Product, Paiement_stripe, LigneArticle
        from PaiementCawl.models import CawlPayment
        with tenant_context(venue):
            product = Product.objects.get(asset=currency, methode_caisse=Product.RECHARGE_EUROS)
            price_sold = get_or_create_price_sold(product.prices.get(free_price=True),
                                                 custom_amount=Decimal(amount)/100)
            payment = Paiement_stripe.objects.create(user=self.user)
            line = LigneArticle.objects.create(pricesold=price_sold, qty=1, amount=amount)
            payment.lignearticles.add(line)
            CawlPayment.objects.create(payment=payment, merchant_id='isolated', amount=amount, test_mode=True)
            Paiement_stripe.objects.filter(pk=payment.pk).update(status=Paiement_stripe.PAID, montant_encaisse=amount)
            payment.refresh_from_db()
            return payment

    def test_online_and_stand_topups_share_one_currency_with_separate_refund_caps_per_gala(self):
        from fedow_core.services import TransactionService, WalletService
        from PaiementCawl.recharges import crediter_la_recharge
        from PaiementCawl.remboursements import calculer_le_remboursable
        currency_b = self.isolate_two_editions()
        Token.objects.filter(wallet=self.wallet, asset=self.asset).update(value=0)
        payment = self.paid_topup(self.asset, self.tenant, 2000)
        self.config.live_venue = self.other
        self.config.save(update_fields=['live_venue'])
        with tenant_context(self.tenant):
            tx = crediter_la_recharge(payment)
            self.assertEqual(tx.asset_id, self.asset.pk)
            self.assertEqual(crediter_la_recharge(payment).pk, tx.pk)
            TransactionService.creer_recharge(sender_wallet=self.owner, receiver_wallet=self.wallet,
                                             asset=self.asset, montant_en_centimes=1000, tenant=self.tenant)
            TransactionService.creer_vente(sender_wallet=self.wallet, receiver_wallet=self.owner,
                                           asset=self.asset, montant_en_centimes=1500, tenant=self.tenant)
            result = calculer_le_remboursable(self.user)
            self.assertEqual((result.solde, result.en_ligne, result.sur_place), (1500, 1500, 0))
        with tenant_context(self.other):
            TransactionService.creer_recharge(sender_wallet=currency_b.wallet_origin, receiver_wallet=self.wallet,
                                             asset=currency_b, montant_en_centimes=700, tenant=self.other)
            result = calculer_le_remboursable(self.user)
            self.assertEqual((result.solde, result.en_ligne, result.sur_place), (700, 0, 700))
            result = WalletService.rembourser_en_especes(self.card, self.other, currency_b.wallet_origin)
            self.assertEqual(result['total_centimes'], 700)
        self.assertEqual(WalletService.obtenir_solde(self.wallet, self.asset), 1500)
        self.assertEqual(WalletService.obtenir_solde(self.wallet, currency_b), 0)
        self.card.refresh_from_db()
        self.assertEqual(self.card.user_id, self.user.pk)

    def test_currency_binding_cannot_be_changed_to_another_gala_or_removed(self):
        currency_b = self.isolate_two_editions()
        for replacement in (currency_b, None):
            self.edition.currency = replacement
            with self.assertRaises(ValidationError):
                self.edition.save()
        self.edition.refresh_from_db()
        self.assertEqual(self.edition.currency_id, self.asset.pk)
        with self.assertRaises(ValidationError):
            self.edition.currency_isolated = False
            self.edition.save()
