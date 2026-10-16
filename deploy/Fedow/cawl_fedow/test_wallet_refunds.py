import base64
import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import Mock, patch
from uuid import uuid4

from django.db import close_old_connections, connections
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from cawl_fedow.models import Checkout, WalletRefund, WalletRefundRequest
from cawl_fedow.refunds import (
    finish_wallet_refund, prepare_wallet_refund, reconcile_pending_refunds,
    reconcile_wallet_refund, refund_summary,
)
from cawl_fedow.services import credit_checkout
from fedow_core.models import (
    Asset, Configuration, Federation, FedowUser, OrganizationAPIKey, Place,
    Token, Transaction, Wallet, asset_creator,
)
from payment_providers.cawl import CawlConfiguration, CawlError, CawlGateway, PaymentSnapshot


class RefundFixture:
    def setUp(self):
        super().setUp()
        self.primary = Wallet.objects.create(name='QA Primary')
        Configuration.objects.create(name='QA', domain='fedow.example.test', primary_wallet=self.primary)
        self.asset = asset_creator(name='QA euros', currency_code='FED', category=Asset.STRIPE_FED_FIAT,
                                   wallet_origin=self.primary)
        self.wallet = Wallet.objects.create(name='Refund QA')
        FedowUser.objects.create(username='refund-qa', email='refund@example.test', wallet=self.wallet)
        self.place = Place.objects.create(name='QA Gala', wallet=Wallet.objects.create(), lespass_domain='gala.example.test')
        federation = Federation.objects.create(name='QA Federation')
        federation.assets.add(self.asset)
        federation.places.add(self.place)
        self.request = RequestFactory().post('/wallet/refund_fed_by_signature/')
        self.request.wallet, self.request.place = self.wallet, self.place
        self.config = CawlConfiguration('qa-merchant', 'key', 'secret', 'hook', 'hook-secret', True)
        self.payments, self.responses = {}, {}
        self.gateway = Mock(configuration=self.config)
        self.gateway.get_payment.side_effect = lambda pk: self.payments[pk]
        self.gateway.get_refunds.side_effect = lambda pk: list(self.responses.get(pk, []))
        self.gateway.refund.side_effect = self.provider_refund
        self.gateway.verify_webhook.side_effect = CawlGateway(self.config).verify_webhook
        for name in ('services', 'refunds', 'views'):
            mock = patch('cawl_fedow.' + name + '.gateway', return_value=self.gateway)
            mock.start()
            self.addCleanup(mock.stop)

    def provider_refund(self, payment_id, amount, operation_id, operation_reference=None):
        response = {
            'id': 'refund-' + str(operation_id), 'status': 'REFUNDED',
            'refundOutput': {'amountOfMoney': {'amount': amount, 'currencyCode': 'EUR'},
                             'operationReferences': {'merchantReference': operation_reference}},
        }
        self.responses.setdefault(payment_id, []).append(response)
        return response

    def recharge(self, amount=2000):
        checkout = Checkout.objects.create(wallet=self.wallet, place=self.place, asset=self.asset,
            merchant_id=self.config.merchant_id, test_mode=True, amount=amount,
            hosted_checkout_id='hosted-' + uuid4().hex)
        snapshot = PaymentSnapshot('payment-' + uuid4().hex, str(checkout.pk), amount, 'EUR', 'CAPTURED')
        self.payments[snapshot.id] = snapshot
        credit_checkout(checkout, self.request, snapshot)
        checkout.refresh_from_db()
        return checkout

    def balance(self):
        return Token.objects.get(wallet=self.wallet, asset=self.asset).value

    def spend(self, amount):
        return Transaction.objects.create(sender=self.wallet, receiver=self.place.wallet, asset=self.asset,
            amount=amount, action=Transaction.QRCODE_SALE, ip='127.0.0.1')

    def reserve(self, request_id=None):
        return prepare_wallet_refund(self.request, request_id or uuid4())[0]


@override_settings(PAYMENT_PROVIDER='cawl', ROOT_URLCONF='cawl_fedow.urls')
class WalletRefundTests(RefundFixture, TestCase):
    def test_refunds_only_unspent_amount_using_native_ledger(self):
        self.recharge()
        self.spend(1200)
        batch = self.reserve()
        self.assertEqual(batch.amount, 800)
        self.assertEqual(self.balance(), 0)
        self.gateway.refund.assert_not_called()  # HTTP only persists the durable request.
        reconcile_pending_refunds()
        self.assertEqual(refund_summary(batch)['refunded'], 800)
        self.assertEqual(self.gateway.refund.call_args.args[1], 800)
        self.assertEqual(Transaction.objects.filter(action=Transaction.CREATION).count(), 1)
        self.assertEqual(Transaction.objects.filter(action=Transaction.REFILL).count(), 1)
        self.assertTrue(all(entry.verify_hash() for entry in Transaction.objects.all()))

    def test_allocates_multiple_recharges_without_exceeding_any_payment(self):
        self.recharge(500)
        self.recharge(500)
        self.spend(200)
        batch = self.reserve()
        self.assertEqual(sorted(batch.refunds.values_list('amount', flat=True)), [300, 500])
        reconcile_pending_refunds()
        self.assertEqual(refund_summary(batch)['refunded'], 800)
        self.assertEqual(self.balance(), 0)

    def test_same_request_never_refunds_twice_even_after_another_recharge(self):
        self.recharge()
        batch = self.reserve()
        reconcile_pending_refunds()
        self.recharge(500)
        replay, created = prepare_wallet_refund(self.request, batch.pk)
        self.assertFalse(created)
        self.assertEqual(replay.pk, batch.pk)
        self.assertEqual(self.balance(), 500)
        self.assertEqual(WalletRefundRequest.objects.count(), 1)
        self.assertEqual(self.gateway.refund.call_count, 1)

    def test_another_request_is_blocked_while_outcome_is_pending(self):
        self.recharge()
        self.reserve()
        with self.assertRaises(CawlError):
            self.reserve()
        self.assertEqual(WalletRefundRequest.objects.count(), 1)

    def test_bank_rejection_releases_exactly_once_and_allows_a_new_request(self):
        self.recharge()
        batch = self.reserve()
        refund = batch.refunds.get()
        response = self.provider_refund(refund.checkout.provider_payment_id, refund.amount, refund.pk, refund.pk.hex)
        response['status'] = 'REJECTED'
        for _ in range(3):
            finish_wallet_refund(refund, response)
        self.assertEqual(self.balance(), 2000)
        self.assertEqual(Transaction.objects.filter(action=Transaction.CORRECTION).count(), 1)
        self.assertEqual(refund_summary(batch)['released'], 2000)
        self.assertEqual(self.reserve().amount, 2000)

    def test_lost_response_recovers_by_operation_reference_without_second_submission(self):
        self.recharge()
        batch = self.reserve()
        def accepted_then_timeout(*args, **kwargs):
            self.provider_refund(*args, **kwargs)
            raise TimeoutError()
        self.gateway.refund.side_effect = accepted_then_timeout
        reconcile_pending_refunds()
        self.assertEqual(refund_summary(batch)['pending'], 2000)
        self.assertEqual(self.balance(), 0)
        reconcile_pending_refunds()
        self.assertEqual(refund_summary(batch)['refunded'], 2000)
        self.assertEqual(self.gateway.refund.call_count, 1)

    def test_unknown_outcome_stays_reserved_and_retry_uses_the_same_key(self):
        self.recharge()
        batch = self.reserve()
        self.gateway.refund.side_effect = TimeoutError()
        reconcile_pending_refunds()
        first_call = self.gateway.refund.call_args
        reconcile_pending_refunds()  # Lease prevents rapid re-submission.
        self.assertEqual(self.gateway.refund.call_count, 1)
        WalletRefund.objects.update(last_attempt_at=timezone.now() - timedelta(minutes=3))
        self.gateway.refund.side_effect = self.provider_refund
        reconcile_pending_refunds()
        self.assertEqual(self.gateway.refund.call_args, first_call)
        self.assertEqual(refund_summary(batch)['refunded'], 2000)
        self.assertEqual(self.balance(), 0)

    def test_no_resubmission_after_the_provider_idempotence_window(self):
        self.recharge()
        batch = self.reserve()
        WalletRefund.objects.update(first_attempt_at=timezone.now() - timedelta(hours=25))
        reconcile_pending_refunds()
        self.gateway.refund.assert_not_called()
        self.assertEqual(refund_summary(batch)['status'], 'REVIEW')
        self.assertEqual(self.balance(), 0)

    def test_confirmed_refund_can_be_recovered_even_after_24_hours(self):
        self.recharge()
        batch = self.reserve()
        refund = batch.refunds.get()
        WalletRefund.objects.update(first_attempt_at=timezone.now() - timedelta(hours=25), status='REVIEW')
        self.provider_refund(refund.checkout.provider_payment_id, refund.amount, refund.pk, refund.pk.hex)
        reconcile_pending_refunds()
        self.assertEqual(refund_summary(batch)['refunded'], 2000)
        self.gateway.refund.assert_not_called()

    def test_pending_provider_state_is_not_reported_as_refunded(self):
        self.recharge()
        batch = self.reserve()
        refund = batch.refunds.get()
        response = self.provider_refund(refund.checkout.provider_payment_id, refund.amount, refund.pk, refund.pk.hex)
        response['status'] = 'REFUND_REQUESTED'
        reconcile_pending_refunds()
        self.assertEqual(refund_summary(batch)['pending'], 2000)
        self.assertEqual(refund_summary(batch)['refunded'], 0)
        self.assertEqual(self.balance(), 0)

    def test_inconsistent_response_cannot_finalize_or_restore_money(self):
        self.recharge()
        batch = self.reserve()
        refund = batch.refunds.get()
        response = self.provider_refund(refund.checkout.provider_payment_id, refund.amount, refund.pk, refund.pk.hex)
        for money in ({'amount': 2001, 'currencyCode': 'EUR'}, {'amount': 2000, 'currencyCode': 'USD'},
                      {'amount': True, 'currencyCode': 'EUR'}):
            response['refundOutput']['amountOfMoney'] = money
            with self.assertRaises(CawlError):
                finish_wallet_refund(refund, response)
        self.assertEqual(self.balance(), 0)
        self.assertEqual(refund_summary(batch)['pending'], 2000)

    def test_portal_refund_outside_our_journal_blocks_new_submission(self):
        checkout = self.recharge()
        batch = self.reserve()
        self.responses[checkout.provider_payment_id] = [{'id': 'portal-refund', 'status': 'REFUNDED'}]
        reconcile_pending_refunds()
        self.gateway.refund.assert_not_called()
        self.assertEqual(refund_summary(batch)['status'], 'REVIEW')

    def test_account_or_test_mode_change_cannot_send_a_refund(self):
        self.recharge()
        batch = self.reserve()
        self.gateway.configuration = CawlConfiguration('other', 'key', 'secret', 'hook', 'hook-secret', False)
        reconcile_pending_refunds()
        self.gateway.get_refunds.assert_not_called()
        self.gateway.refund.assert_not_called()
        self.assertEqual(self.balance(), 0)
        self.assertEqual(refund_summary(batch)['pending'], 2000)

    def test_funds_without_a_matching_original_payment_are_not_debited(self):
        self.recharge()
        Checkout.objects.update(merchant_id='other-account')
        with self.assertRaises(CawlError):
            self.reserve()
        self.assertEqual(self.balance(), 2000)
        self.assertFalse(WalletRefund.objects.exists())

    def test_invalid_ledger_hash_rolls_back_entire_reservation(self):
        self.recharge()
        with patch.object(Transaction, 'verify_hash', return_value=False):
            with self.assertRaises(Exception):
                self.reserve()
        self.assertEqual(self.balance(), 2000)
        self.assertFalse(WalletRefundRequest.objects.exists())
        self.assertFalse(Transaction.objects.filter(action=Transaction.REFUND).exists())

    def test_reserved_balance_cannot_be_spent_while_bank_is_pending(self):
        self.recharge()
        self.reserve()
        with self.assertRaises(ValueError):
            self.spend(100)
        self.assertEqual(self.balance(), 0)
        self.assertFalse(Transaction.objects.filter(action=Transaction.QRCODE_SALE).exists())

    def test_request_id_from_another_wallet_cannot_be_reused(self):
        self.recharge()
        batch = self.reserve()
        self.request.wallet = Wallet.objects.create(name='Other QA')
        with self.assertRaises(CawlError):
            prepare_wallet_refund(self.request, batch.pk)

    def test_empty_request_is_durable_and_cannot_refund_a_later_recharge(self):
        batch = self.reserve()
        self.recharge()
        prepare_wallet_refund(self.request, batch.pk)
        self.assertEqual(self.balance(), 2000)
        self.assertEqual(refund_summary(batch)['status'], 'EMPTY')

    def test_local_currency_is_preserved_while_online_balance_is_refunded(self):
        self.recharge(800)
        local = asset_creator(name='QA local', currency_code='EUR', category=Asset.TOKEN_LOCAL_FIAT,
                              wallet_origin=self.place.wallet)
        token = Token.objects.create(wallet=self.wallet, asset=local, value=700)
        batch = self.reserve()
        reconcile_pending_refunds()
        token.refresh_from_db()
        self.assertEqual(token.value, 700)
        self.assertEqual(refund_summary(batch)['refunded'], 800)

    def test_partial_bank_rejection_restores_only_the_rejected_allocation(self):
        self.recharge(500)
        self.recharge(500)
        self.spend(200)
        batch = self.reserve()
        for index, refund in enumerate(batch.refunds.order_by('-amount')):
            response = self.provider_refund(refund.checkout.provider_payment_id, refund.amount, refund.pk, refund.pk.hex)
            if index:
                response['status'] = 'REJECTED'
            finish_wallet_refund(refund, response)
        self.assertEqual(refund_summary(batch)['status'], 'PARTIAL')
        self.assertEqual(refund_summary(batch)['refunded'], 500)
        self.assertEqual(refund_summary(batch)['released'], 300)
        self.assertEqual(self.balance(), 300)
        second = self.reserve()
        self.assertEqual(second.amount, 300)
        self.assertEqual(second.refunds.count(), 1)

    def signed_client(self):
        from fedow_core.utils import rsa_generator, get_private_key, sign_message, data_to_b64

        private, public = rsa_generator()
        self.wallet.public_pem = public
        self.wallet.save(update_fields=['public_pem'])
        _, key = OrganizationAPIKey.objects.create_key(name='QA refund key', place=self.place, user=self.wallet.user)
        data = {'request_id': str(uuid4())}
        headers = {'HTTP_DATE': timezone.now().isoformat(), 'HTTP_AUTHORIZATION': 'Api-Key ' + key,
                   'HTTP_WALLET': str(self.wallet.pk),
                   'HTTP_SIGNATURE': sign_message(data_to_b64(data), get_private_key(private)).decode()}
        return APIClient(), data, headers

    def test_real_native_place_key_and_wallet_signature_authorize_the_post(self):
        self.recharge()
        client, data, headers = self.signed_client()
        response = client.post('/wallet/refund_fed_by_signature/', data, format='json', **headers)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data['pending'], 2000)
        self.assertEqual(self.balance(), 0)
        self.gateway.refund.assert_not_called()

    def test_missing_signature_and_tampered_body_cannot_debit_a_wallet(self):
        self.recharge()
        client, data, headers = self.signed_client()
        for changes in ({'HTTP_SIGNATURE': ''}, {'HTTP_AUTHORIZATION': 'Api-Key invalid'}):
            response = client.post('/wallet/refund_fed_by_signature/', data, format='json', **{**headers, **changes})
            self.assertEqual(response.status_code, 403)
        response = client.post('/wallet/refund_fed_by_signature/', {'request_id': str(uuid4())}, format='json', **headers)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.balance(), 2000)
        self.assertFalse(WalletRefund.objects.exists())

    def test_get_cannot_trigger_a_refund(self):
        self.recharge()
        response = APIClient().get('/wallet/refund_fed_by_signature/')
        self.assertIn(response.status_code, (403, 405))
        self.assertEqual(self.balance(), 2000)
        self.assertFalse(WalletRefund.objects.exists())

    def test_refund_webhook_replay_uses_authoritative_state_once(self):
        self.recharge()
        batch = self.reserve()
        refund = batch.refunds.get()
        response = self.provider_refund(refund.checkout.provider_payment_id, refund.amount, refund.pk, refund.pk.hex)
        event = {'apiVersion': 'v1', 'id': str(uuid4()), 'type': 'refund.refunded',
                 'merchantId': self.config.merchant_id, 'refund': response}
        body = json.dumps(event).encode()
        signature = base64.b64encode(hmac.new(self.config.webhook_secret.encode(), body, hashlib.sha256).digest()).decode()
        for _ in range(3):
            result = APIClient().post('/webhook_cawl/', body, content_type='application/json',
                HTTP_X_GCS_KEYID=self.config.webhook_key_id, HTTP_X_GCS_SIGNATURE=signature)
            self.assertEqual(result.status_code, 200)
        self.assertEqual(refund_summary(batch)['refunded'], 2000)
        self.assertEqual(Transaction.objects.filter(action=Transaction.REFUND).count(), 1)
        self.gateway.refund.assert_not_called()

    def test_final_payment_refunded_webhook_confirms_a_partial_refund_without_minting(self):
        self.recharge(2000)
        self.spend(1200)
        batch = self.reserve()
        refund = batch.refunds.get()
        response = self.provider_refund(refund.checkout.provider_payment_id, 800, refund.pk, refund.pk.hex)
        response['status'] = 'REFUND_REQUESTED'
        finish_wallet_refund(refund, response)
        response['status'] = 'REFUNDED'
        # The documented final event contains payment, with the refund operation
        # ID and refund amount, rather than the initial 2,000-cent capture.
        event = {'apiVersion': 'v1', 'id': str(uuid4()), 'type': 'payment.refunded',
                 'merchantId': self.config.merchant_id, 'payment': {
                     'id': response['id'], 'status': 'REFUNDED', 'paymentOutput': {
                         'amountOfMoney': {'amount': 800, 'currencyCode': 'EUR'},
                         'references': {'merchantReference': str(refund.checkout_id)}}}}
        body = json.dumps(event).encode()
        signature = base64.b64encode(hmac.new(self.config.webhook_secret.encode(), body, hashlib.sha256).digest()).decode()
        for _ in range(2):
            result = APIClient().post('/webhook_cawl/', body, content_type='application/json',
                HTTP_X_GCS_KEYID=self.config.webhook_key_id, HTTP_X_GCS_SIGNATURE=signature)
            self.assertEqual(result.status_code, 200)
        self.assertEqual(refund_summary(batch)['refunded'], 800)
        self.assertEqual(self.balance(), 0)
        self.assertEqual(Transaction.objects.filter(action=Transaction.CREATION).count(), 1)
        self.assertEqual(Transaction.objects.filter(action=Transaction.REFUND).count(), 1)
        self.gateway.get_payment.assert_not_called()


@override_settings(PAYMENT_PROVIDER='cawl')
class WalletRefundConcurrencyTests(RefundFixture, TransactionTestCase):
    def test_concurrent_confirmations_reserve_exactly_once(self):
        self.recharge()
        request_id = uuid4()
        barrier = Barrier(2)
        def reserve():
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                return prepare_wallet_refund(self.request, request_id)[1]
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: reserve(), range(2)))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(self.balance(), 0)
        self.assertEqual(WalletRefund.objects.count(), 1)
        self.assertEqual(Transaction.objects.filter(action=Transaction.REFUND).count(), 1)

    def test_concurrent_workers_submit_the_same_allocation_once(self):
        self.recharge()
        refund = self.reserve().refunds.select_related('request', 'checkout').get()
        barrier = Barrier(2)
        def read_refunds(_payment):
            barrier.wait(timeout=5)
            return []
        self.gateway.get_refunds.side_effect = read_refunds
        def reconcile():
            close_old_connections()
            try:
                reconcile_wallet_refund(refund)
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(lambda _: reconcile(), range(2)))
        self.assertEqual(self.gateway.refund.call_count, 1)
        self.assertEqual(self.balance(), 0)
        refund.refresh_from_db()
        self.assertEqual(refund.status, 'REFUNDED')
