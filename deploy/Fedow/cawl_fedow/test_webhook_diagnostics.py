"""Validate signed provider diagnostics without using the ledger or bank API."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase

from payment_providers.cawl import CawlError
from cawl_fedow.views import webhook


class WebhookDiagnosticTests(SimpleTestCase):
    def test_verified_provider_diagnostic_has_no_bank_or_database_effect(self):
        request = RequestFactory().post('/webhook_cawl/')
        gateway = SimpleNamespace(verify_webhook=Mock(return_value={
            'id': 'qa-diagnostic', 'type': 'payment.test', 'payment': {'id': '9999_9'}}),
            get_payment=Mock(side_effect=AssertionError('diagnostic must not read a bank payment')))
        with patch('cawl_fedow.views.gateway', return_value=gateway):
            self.assertEqual(webhook(request).status_code, 200)
            gateway.verify_webhook.assert_called_once()
            gateway.get_payment.assert_not_called()
            gateway.verify_webhook.side_effect = CawlError('invalid signature or merchant')
            self.assertEqual(webhook(request).status_code, 400)
