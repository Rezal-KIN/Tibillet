from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.utils import timezone
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.utils import tenant_context
from rest_framework.exceptions import ValidationError

from BaseBillet.models import Configuration, Event, LigneArticle, Paiement_stripe, Price, PriceSold, Product, ProductSold, Reservation
from PaiementCawl.models import CawlRefund
from PaiementCawl.refunds import cancel_reservation, finish_refund
from PaiementCawl.services import CreationPaiementCawl, checkout_session, update_payment
from payment_providers.cawl import CawlConfiguration, CawlError, HostedCheckout, PaymentSnapshot


class WalletRefundViewTests(SimpleTestCase):
    def request(self):
        from django.contrib.messages.storage.fallback import FallbackStorage

        request = RequestFactory().get('/my_account/refund_online/')
        request.user = SimpleNamespace(email='refund-qa@example.test',
                                       wallet=SimpleNamespace(uuid=uuid4()),
                                       full_name=lambda: 'Refund QA')
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    @override_settings(PAYMENT_PROVIDER='cawl')
    def test_cawl_wallet_refund_stops_before_the_unsupported_fedow_call(self):
        from BaseBillet.views import MyAccount

        request = self.request()
        with patch('BaseBillet.views.FedowAPI') as fedow:
            response = MyAccount().refund_online(request)
        fedow.assert_not_called()
        self.assertEqual(response['HX-Redirect'], '/my_account/balance/')
        self.assertIn('Contactez le collectif', str(list(request._messages)[0]))

    @override_settings(PAYMENT_PROVIDER='stripe')
    def test_stripe_wallet_refund_keeps_the_native_request_and_confirmation(self):
        from BaseBillet.views import MyAccount

        request = self.request()
        with patch('BaseBillet.views.FedowAPI') as fedow, \
                patch('BaseBillet.views.send_email_generique.delay') as confirmation:
            wallet = fedow.return_value.wallet
            wallet.cached_retrieve_by_signature.return_value.validated_data = {
                'tokens': [{'asset': {'is_stripe_primary': True}, 'value': 500}],
            }
            wallet.refund_fed_by_signature.return_value = (202, {})
            response = MyAccount().refund_online(request)
        wallet.refund_fed_by_signature.assert_called_once_with(request.user)
        confirmation.assert_called_once()
        self.assertEqual(response['HX-Redirect'], '/my_account/')


class PaymentTests(FastTenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = 'CAWL isolated tests'

    def setUp(self):
        # FastTenantTestCase overrides setUpClass without Django's settings hook.
        self.enterContext(override_settings(PAYMENT_PROVIDER='cawl', SOLO_CACHE=None))
        self.task_patch = patch('celery.app.task.Task.apply_async')
        self.task_patch.start()
        self.addCleanup(self.task_patch.stop)
        self.context = tenant_context(self.tenant)
        self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)
        self.user = get_user_model().objects.create(username=str(uuid4()), email=f'{uuid4()}@example.test')
        from django.db import connection
        connection.set_tenant(self.tenant)
        self.product = Product.objects.create(name='QA', categorie_article=Product.NONE)
        self.price = Price.objects.create(product=self.product, name='QA', prix=5)
        self.sold = PriceSold.objects.create(price=self.price, productsold=ProductSold.objects.create(product=self.product), prix=5)
        self.event = Event.objects.create(name='CAWL QA ' + uuid4().hex, datetime=timezone.now())
        self.reservation = Reservation.objects.create(user_commande=self.user, event=self.event)
        self.line = LigneArticle.objects.create(pricesold=self.sold, qty=1, amount=500, reservation=self.reservation)
        self.gateway = SimpleNamespace(configuration=CawlConfiguration('merchant', 'key', 'secret', 'hook', 'hook-secret', True))
        from unittest.mock import Mock
        self.gateway.create_checkout = Mock(side_effect=lambda **kwargs: HostedCheckout(
            'hosted-' + uuid4().hex, 'https://payment.preprod.cawl-solutions.fr/qa', 'mac'))
        self.gateway_patch = patch('PaiementCawl.services.gateway', return_value=self.gateway)
        self.gateway_patch.start()
        self.addCleanup(self.gateway_patch.stop)

    def create(self):
        return CreationPaiementCawl(self.user, [self.line], {}, self.reservation,
            source=Paiement_stripe.FRONT_BILLETTERIE, absolute_domain='https://gala.example/event/', success_url='stripe_return/')

    def test_cawl_checkout_preserves_sale_and_has_no_stripe_identifier(self):
        with patch('stripe.checkout.Session.create') as stripe_create:
            creation = self.create()
        self.line.refresh_from_db()
        self.assertEqual(self.line.payment_method, 'CW')
        self.assertEqual(creation.paiement_stripe_db.cawl_payment.amount, 500)
        self.assertIsNone(creation.paiement_stripe_db.checkout_session_id_stripe)
        stripe_create.assert_not_called()

    def test_repeated_request_cannot_create_a_second_checkout(self):
        self.create()
        with self.assertRaises(ValidationError):
            self.create()
        self.assertEqual(self.gateway.create_checkout.call_count, 1)

    def test_recurring_price_is_rejected_before_any_remote_request(self):
        self.price.recurring_payment = True
        self.price.save(update_fields=['recurring_payment'])
        with self.assertRaises(ValidationError):
            self.create()
        self.gateway.create_checkout.assert_not_called()

    def test_other_currency_is_rejected_before_any_remote_request(self):
        config = Configuration.get_solo()
        config.currency_code = 'USD'
        config.save()
        with self.assertRaises(ValidationError):
            self.create()
        self.gateway.create_checkout.assert_not_called()

    def test_requested_refund_does_not_book_a_credit_until_confirmed(self):
        creation = self.create()
        record = creation.paiement_stripe_db.cawl_payment
        Paiement_stripe.objects.filter(pk=record.pk).update(status=Paiement_stripe.VALID)
        refund = CawlRefund.objects.create(operation_id=uuid4(), payment=record,
            amount=500, provider_refund_id='refund-1', allocations=[{'line': str(self.line.pk), 'qty': '1'}])
        response = {'id': 'refund-1', 'status': 'REFUND_REQUESTED',
                    'refundOutput': {'amountOfMoney': {'amount': 500, 'currencyCode': 'EUR'}}}
        with patch('BaseBillet.signals.send_refund_to_laboutik.delay'):
            finish_refund(refund, response)
            self.assertFalse(LigneArticle.objects.filter(qty__lt=0).exists())
            response['status'] = 'REFUNDED'
            finish_refund(refund, response)
            finish_refund(refund, response)
        self.assertEqual(LigneArticle.objects.filter(qty__lt=0).count(), 1)

    def test_captured_ticket_sale_is_finalised_once_across_replays(self):
        self.product.categorie_article = Product.BILLET
        self.product.save(update_fields=['categorie_article'])
        payment = self.create().paiement_stripe_db
        snapshot = PaymentSnapshot('captured-1', str(payment.pk), 500, 'EUR', 'CAPTURED')
        with patch('BaseBillet.triggers.send_sale_to_laboutik.delay') as send_sale:
            for _ in range(3):
                self.assertEqual(update_payment(payment, snapshot), Paiement_stripe.VALID)
        self.line.refresh_from_db()
        self.assertEqual(self.line.status, LigneArticle.VALID)
        self.assertEqual(send_sale.call_count, 1)

    def test_late_rejection_cannot_downgrade_a_captured_payment(self):
        payment = self.create().paiement_stripe_db
        capture = PaymentSnapshot('captured-1', str(payment.pk), 500, 'EUR', 'CAPTURED')
        update_payment(payment, capture)
        payment.refresh_from_db()
        Paiement_stripe.objects.filter(pk=payment.pk).update(traitement_en_cours=False)
        late = PaymentSnapshot('rejected-2', str(payment.pk), 500, 'EUR', 'REJECTED')
        self.assertEqual(update_payment(payment, late), Paiement_stripe.PAID)
        self.assertEqual(payment.cawl_payment.provider_payment_id, 'captured-1')

    def test_rejected_refund_does_not_cancel_the_reservation(self):
        payment = self.create().paiement_stripe_db
        Paiement_stripe.objects.filter(pk=payment.pk).update(status=Paiement_stripe.VALID)
        payment.cawl_payment.provider_payment_id = 'captured-1'
        payment.cawl_payment.save(update_fields=['provider_payment_id'])
        LigneArticle.objects.filter(pk=self.line.pk).update(status=LigneArticle.VALID)
        response = {'id': 'rejected-refund', 'status': 'REJECTED',
                    'refundOutput': {'amountOfMoney': {'amount': 500, 'currencyCode': 'EUR'}}}
        from unittest.mock import Mock
        self.gateway.refund = Mock(return_value=response)
        with patch('PaiementCawl.refunds.gateway', return_value=self.gateway):
            with self.assertRaises(CawlError):
                cancel_reservation(self.reservation)
        self.reservation.refresh_from_db()
        self.assertNotEqual(self.reservation.status, Reservation.CANCELED)
        self.assertFalse(LigneArticle.objects.filter(qty__lt=0).exists())

    def test_failed_checkout_creation_releases_the_order(self):
        self.gateway.create_checkout.side_effect = [RuntimeError('network'), HostedCheckout(
            'hosted-' + uuid4().hex, 'https://payment.preprod.cawl-solutions.fr/qa', 'mac')]
        with self.assertRaises(ValidationError):
            self.create()
        self.assertEqual(Paiement_stripe.objects.get(reservation=self.reservation).status, Paiement_stripe.CANCELED)
        # FR : La commande libérée n'empêche pas un nouvel essai. / Retry is possible.
        self.create()
        self.assertEqual(self.gateway.create_checkout.call_count, 2)

    def test_abandoned_checkout_expires_and_allows_a_new_attempt(self):
        from datetime import timedelta
        from PaiementCawl.models import CawlPayment

        payment = self.create().paiement_stripe_db
        self.gateway.get_checkout = lambda checkout_id: ('IN_PROGRESS', None)
        self.assertEqual(update_payment(payment), Paiement_stripe.PENDING)
        CawlPayment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(hours=2))
        payment.refresh_from_db()
        self.assertEqual(update_payment(payment), Paiement_stripe.EXPIRE)
        self.create()
        self.assertEqual(self.gateway.create_checkout.call_count, 2)

    def test_failed_checkout_cannot_be_reused_as_an_open_membership_session(self):
        payment = self.create().paiement_stripe_db
        for status in ('REJECTED', 'REJECTED_CAPTURE', 'CANCELLED'):
            with self.subTest(status=status):
                snapshot = PaymentSnapshot('payment-1', str(payment.pk), 500, 'EUR', status)
                self.gateway.get_checkout = lambda checkout_id: ('PAYMENT_CREATED', snapshot)
                session = checkout_session(payment)
                self.assertEqual(session.status, 'expired')
                self.assertEqual(session.payment_status, 'unpaid')

    def test_processing_payment_is_not_reopened_after_checkout_timeout(self):
        from datetime import timedelta
        from PaiementCawl.models import CawlPayment

        payment = self.create().paiement_stripe_db
        CawlPayment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(hours=2))
        payment.refresh_from_db()
        snapshot = PaymentSnapshot('payment-1', str(payment.pk), 500, 'EUR', 'CAPTURE_REQUESTED')
        self.gateway.get_checkout = lambda checkout_id: ('PAYMENT_CREATED', snapshot)
        session = checkout_session(payment)
        self.assertEqual(session.status, 'complete')
        self.assertEqual(session.payment_status, 'unpaid')

    def test_refund_cap_includes_previous_refunds(self):
        payment = self.create().paiement_stripe_db
        Paiement_stripe.objects.filter(pk=payment.pk).update(status=Paiement_stripe.VALID)
        payment.cawl_payment.provider_payment_id = 'captured-1'
        payment.cawl_payment.save(update_fields=['provider_payment_id'])
        LigneArticle.objects.filter(pk=self.line.pk).update(status=LigneArticle.VALID)
        CawlRefund.objects.create(operation_id=uuid4(), payment=payment.cawl_payment, amount=500,
            provider_refund_id='refund-earlier', status='REFUND_REQUESTED', allocations=[])
        from unittest.mock import Mock
        self.gateway.refund = Mock()
        with patch('PaiementCawl.refunds.gateway', return_value=self.gateway):
            with self.assertRaises(CawlError):
                cancel_reservation(self.reservation)
        self.gateway.refund.assert_not_called()
