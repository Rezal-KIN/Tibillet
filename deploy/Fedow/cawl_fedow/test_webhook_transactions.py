"""Provider latency must not hold the SQLite ledger's write transaction."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.db import connection
from django.test import TransactionTestCase

from cawl_fedow import tests as ledger_tests
from cawl_fedow.models import Webhook
from cawl_fedow.services import credit_checkout
from cawl_fedow.views import webhook
from fedow_core.models import Token, Transaction
from payment_providers.cawl import CawlConfiguration


class WebhookTransactionTests(TransactionTestCase):
    def setUp(self):
        ledger_tests.LedgerTests.setUp(self)
        self.gateway = SimpleNamespace(
            configuration=CawlConfiguration('qa-merchant', 'key', 'secret', 'hook', 'hook-secret', True),
            verify_webhook=Mock(return_value={
                'id': 'qa-event', 'type': 'payment.captured', 'payment': {'id': 'qa-payment'}}),
            get_payment=Mock(side_effect=self.authoritative_payment),
        )
        self.view_gateway = patch('cawl_fedow.views.gateway', return_value=self.gateway)
        self.view_gateway.start()
        self.addCleanup(self.view_gateway.stop)

    def authoritative_payment(self, payment_id):
        self.assertFalse(connection.in_atomic_block, 'bank read holds a ledger transaction')
        self.assertEqual(payment_id, 'qa-payment')
        return ledger_tests.LedgerTests.snapshot(self)

    def test_bank_read_is_outside_transaction_and_replays_credit_once(self):
        for _ in range(3):
            self.assertEqual(webhook(self.request).status_code, 200)
        self.gateway.get_payment.assert_called_once_with('qa-payment')
        self.assertEqual(Webhook.objects.count(), 1)
        self.assertEqual(Token.objects.get(wallet=self.wallet, asset=self.asset).value, 2000)
        self.assertEqual(Transaction.objects.filter(action=Transaction.CREATION).count(), 1)
        self.assertEqual(Transaction.objects.filter(action=Transaction.REFILL).count(), 1)

    def test_failed_processing_rolls_back_claim_and_credit_before_retry(self):
        def fail_after_credit(*args):
            credit_checkout(*args)
            raise RuntimeError('fictitious processing failure')

        with patch('cawl_fedow.views.credit_checkout', side_effect=fail_after_credit):
            self.assertEqual(webhook(self.request).status_code, 503)
        self.assertFalse(Webhook.objects.exists())
        self.assertFalse(Transaction.objects.filter(action=Transaction.CREATION).exists())
        self.checkout.refresh_from_db()
        self.assertIsNone(self.checkout.refill_id)
        self.assertEqual(webhook(self.request).status_code, 200)
        self.assertEqual(Transaction.objects.filter(action=Transaction.CREATION).count(), 1)
