import io
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command, get_commands
from django.test import TestCase, RequestFactory, override_settings

from cawl_fedow.models import Checkout
from cawl_fedow.services import credit_checkout
from fedow_core.models import Asset, Configuration, FedowUser, Place, Token, Transaction, Wallet, asset_creator
from payment_providers.cawl import CawlConfiguration, CawlError, PaymentSnapshot


@override_settings(PAYMENT_PROVIDER='cawl')
class InstallTests(TestCase):
    def test_first_install_uses_cawl_and_reuses_its_primary_wallet(self):
        from fedow_core.models import Federation

        # Resolve the same command as the native container entrypoint, using
        # the real app order rather than importing our Command directly.
        self.assertEqual(get_commands()['install'], 'cawl_fedow')
        environment = {
            'DOMAIN': 'fedow.example.test', 'STRIPE_KEY': '', 'STRIPE_KEY_TEST': '',
            'CAWL_MERCHANT_ID': 'qa-merchant', 'CAWL_API_KEY_ID': 'qa-key',
            'CAWL_API_SECRET': 'qa-secret', 'CAWL_WEBHOOK_KEY_ID': 'qa-hook',
            'CAWL_WEBHOOK_SECRET': 'qa-hook-secret', 'CAWL_TEST': '1',
        }
        with patch.dict('os.environ', environment):
            call_command('install', stdout=io.StringIO())
            primary_id = Configuration.get_solo().primary_wallet_id
            call_command('install', stdout=io.StringIO())
        self.assertEqual(Configuration.objects.count(), 1)
        self.assertEqual(Configuration.get_solo().primary_wallet_id, primary_id)
        self.assertEqual(Wallet.objects.count(), 1)
        self.assertEqual(Federation.objects.count(), 1)
        self.assertEqual(Asset.objects.get().wallet_origin_id, primary_id)


class LedgerTests(TestCase):
    def setUp(self):
        self.primary = Wallet.objects.create(name='QA Primary')
        Configuration.objects.create(name='QA', domain='fedow.example', primary_wallet=self.primary)
        self.asset = asset_creator(name='QA euros', currency_code='FED', category=Asset.STRIPE_FED_FIAT, wallet_origin=self.primary)
        self.wallet = Wallet.objects.create(name='QA user')
        FedowUser.objects.create(username='qa', email='qa@example.test', wallet=self.wallet)
        self.place = Place.objects.create(name='QA gala', wallet=Wallet.objects.create(), lespass_domain='gala.example')
        self.checkout = Checkout.objects.create(wallet=self.wallet, place=self.place, asset=self.asset,
            merchant_id='qa-merchant', test_mode=True, amount=2000, hosted_checkout_id='qa-hosted')
        self.request = RequestFactory().post('/webhook_cawl/')
        config = CawlConfiguration('qa-merchant', 'key', 'secret', 'hook', 'hook-secret', True)
        self.client_patch = patch('cawl_fedow.services.gateway', return_value=SimpleNamespace(configuration=config))
        self.client_patch.start()
        self.addCleanup(self.client_patch.stop)

    def snapshot(self, status='CAPTURED', amount=2000):
        return PaymentSnapshot('qa-payment', str(self.checkout.pk), amount, 'EUR', status)

    def test_captured_credits_exactly_once_on_replayed_return_and_webhook(self):
        for _ in range(3):
            self.assertTrue(credit_checkout(self.checkout, self.request, self.snapshot()))
        self.assertEqual(Token.objects.get(wallet=self.wallet, asset=self.asset).value, 2000)
        self.assertEqual(Transaction.objects.filter(asset=self.asset, action=Transaction.CREATION).count(), 1)
        self.assertEqual(Transaction.objects.filter(asset=self.asset, action=Transaction.REFILL).count(), 1)
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.refill.receiver_id, self.wallet.pk)

    def test_capture_requested_cannot_create_money(self):
        self.assertFalse(credit_checkout(self.checkout, self.request, self.snapshot('CAPTURE_REQUESTED')))
        self.assertFalse(Transaction.objects.filter(action=Transaction.CREATION).exists())

    def test_amount_mismatch_has_no_ledger_side_effect(self):
        with self.assertRaises(CawlError):
            credit_checkout(self.checkout, self.request, self.snapshot(amount=2001))
        self.assertFalse(Transaction.objects.filter(action=Transaction.CREATION).exists())

    def test_invalid_hash_rolls_back_mint_refill_and_checkout_claim(self):
        with patch.object(Transaction, 'verify_hash', return_value=False):
            with self.assertRaises(Exception):
                credit_checkout(self.checkout, self.request, self.snapshot())
        self.assertFalse(Transaction.objects.filter(action=Transaction.CREATION).exists())
        self.checkout.refresh_from_db()
        self.assertIsNone(self.checkout.refill_id)
        self.assertTrue(credit_checkout(self.checkout, self.request, self.snapshot()))

    def test_another_account_cannot_credit_an_existing_checkout(self):
        self.checkout.merchant_id = 'other-merchant'
        with self.assertRaises(CawlError):
            credit_checkout(self.checkout, self.request, self.snapshot())
        self.assertFalse(Transaction.objects.filter(action=Transaction.CREATION).exists())


class CheckoutCreationTests(TestCase):
    def setUp(self):
        from unittest.mock import Mock
        self.primary = Wallet.objects.create(name='QA Primary')
        Configuration.objects.create(name='QA', domain='fedow.example', primary_wallet=self.primary)
        asset_creator(name='QA euros', currency_code='FED', category=Asset.STRIPE_FED_FIAT, wallet_origin=self.primary)
        self.wallet = Wallet.objects.create(name='QA user')
        FedowUser.objects.create(username='qa', email='qa@example.test', wallet=self.wallet)
        self.place = Place.objects.create(name='QA gala', wallet=Wallet.objects.create(), lespass_domain='gala.example')
        self.request = SimpleNamespace(wallet=self.wallet, place=self.place)
        config = CawlConfiguration('qa-merchant', 'key', 'secret', 'hook', 'hook-secret', True)
        self.gateway = SimpleNamespace(configuration=config, create_checkout=Mock(side_effect=RuntimeError('network')))
        self.client_patch = patch('cawl_fedow.services.gateway', return_value=self.gateway)
        self.client_patch.start()
        self.addCleanup(self.client_patch.stop)

    def test_failed_creation_does_not_block_the_next_refill(self):
        from cawl_fedow.services import create_checkout
        from payment_providers.cawl import HostedCheckout
        with patch.dict('os.environ', {'DOMAIN': 'fedow.example'}):
            with self.assertRaises(CawlError):
                create_checkout(self.request, 2000)
            self.assertFalse(Checkout.objects.exists())
            self.gateway.create_checkout.side_effect = None
            self.gateway.create_checkout.return_value = HostedCheckout(
                'qa-hosted-2', 'https://payment.preprod.cawl-solutions.fr/qa', 'mac')
            checkout = create_checkout(self.request, 2000)
        self.assertEqual(checkout.checkout_url, 'https://payment.preprod.cawl-solutions.fr/qa')
