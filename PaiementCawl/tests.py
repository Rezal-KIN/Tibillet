from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.utils import tenant_context
from rest_framework.exceptions import ValidationError

from BaseBillet.models import Configuration, Event, LigneArticle, Paiement_stripe, Price, PriceSold, Product, ProductSold, Reservation
from PaiementCawl.models import CawlRefund
from PaiementCawl.refunds import cancel_reservation, finish_refund
from PaiementCawl.services import CreationPaiementCawl, update_payment
from payment_providers.cawl import CawlConfiguration, CawlError, HostedCheckout, PaymentSnapshot


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
        self.gateway.create_checkout = Mock(return_value=HostedCheckout('hosted-' + uuid4().hex, 'https://payment.preprod.cawl-solutions.fr/qa', 'mac'))
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
