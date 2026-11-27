"""Historique d'une carte pour le mode gérant : lecture seule, lieu émetteur signé."""
from uuid import uuid4

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from cawl_fedow.models import Checkout
from fedow_core.models import (
    Asset, Card, Configuration, FedowUser, OrganizationAPIKey, Origin, Place, Transaction, Wallet,
    asset_creator,
)
from fedow_core.utils import get_private_key, rsa_generator, sign_message


@override_settings(PAYMENT_PROVIDER='cawl', ROOT_URLCONF='cawl_fedow.urls')
class CardHistoryTests(TestCase):
    def setUp(self):
        self.primary = Wallet.objects.create(name='QA Primary')
        Configuration.objects.create(name='QA', domain='fedow.example.test', primary_wallet=self.primary)
        self.asset = asset_creator(name='QA euros', currency_code='FED', category=Asset.STRIPE_FED_FIAT,
                                   wallet_origin=self.primary)
        private, public = rsa_generator()
        self.private = private
        self.place = Place.objects.create(name='QA Gala', wallet=Wallet.objects.create(name='Gala'),
                                          cashless_rsa_pub_key=public)
        self.other = Place.objects.create(name='Other', wallet=Wallet.objects.create(name='Other'))
        self.user = FedowUser.objects.create(username='holder', email='holder@example.test',
                                             wallet=Wallet.objects.create(name='Holder'))
        self.card = Card.objects.create(first_tag_id='ABCD1234', qrcode_uuid=uuid4(), number_printed='ABCD1234',
                                        origin=Origin.objects.create(place=self.place, generation=2),
                                        wallet_ephemere=Wallet.objects.create(name='Ephemeral'))
        _, self.key = OrganizationAPIKey.objects.create_key(name='QA place', place=self.place, user=self.user)

    def get(self, tag='ABCD1234', key=None, sign=True):
        key = key or self.key
        headers = {'HTTP_AUTHORIZATION': 'Api-Key ' + key}
        if sign:
            headers['HTTP_SIGNATURE'] = sign_message(key.encode('utf8'), get_private_key(self.private)).decode()
        return APIClient().get(f'/card_history/{tag}/', **headers)

    def tx(self, sender, receiver, amount, action):
        # Lecture seule testée : on insère sans rejouer la logique d'écriture native.
        from datetime import timedelta
        from django.utils import timezone
        previous = Transaction.objects.order_by('datetime').last()
        self.clock = getattr(self, 'clock', timezone.now()) + timedelta(seconds=1)
        Transaction.objects.bulk_create([Transaction(
            uuid=uuid4(), hash=uuid4().hex + uuid4().hex, ip='127.0.0.1', sender=sender, receiver=receiver,
            asset=self.asset, amount=amount, action=action, card=self.card, previous_transaction=previous,
            datetime=self.clock)])

    def test_place_sees_refill_sale_and_association_newest_first(self):
        self.tx(self.primary, self.card.wallet_ephemere, 1500, Transaction.REFILL)
        self.tx(self.card.wallet_ephemere, self.place.wallet, 500, Transaction.SALE)
        self.card.user = self.user
        self.card.save()
        self.tx(self.card.wallet_ephemere, self.user.wallet, 1000, Transaction.FUSION)
        response = self.get()
        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertEqual(data['card']['number'], 'ABCD1234')
        self.assertTrue(data['card']['linked_to_account'])
        self.assertEqual(data['card']['email'], 'h***@example.test')
        actions = [(op['action'], op['sign'], op['amount']) for op in data['operations']]
        self.assertEqual(actions, [('FUS', 0, 1000), ('SAL', -1, 500), ('REF', 1, 1500)])
        self.assertEqual(data['operations'][1]['to'], 'QA Gala')
        self.assertEqual(data['operations'][2]['from'], 'Banque')

    def test_online_refill_shows_fee_and_status(self):
        self.card.user = self.user
        self.card.save()
        Checkout.objects.create(wallet=self.user.wallet, place=self.place, asset=self.asset, merchant_id='m',
                                test_mode=True, amount=2000, fee=20, hosted_checkout_id='h1',
                                provider_status='CAPTURED')
        data = self.get().data
        self.assertEqual(data['online_refills'][0]['amount'], 2000)
        self.assertEqual(data['online_refills'][0]['fee'], 20)
        self.assertFalse(data['online_refills'][0]['credited'])

    def test_unsigned_or_unknown_key_is_refused(self):
        self.assertEqual(self.get(sign=False).status_code, 403)
        self.assertEqual(self.get(key='invalid.key').status_code, 403)

    def test_card_of_another_place_is_refused(self):
        self.card.origin = Origin.objects.create(place=self.other, generation=1)
        self.card.save()
        self.assertEqual(self.get().status_code, 403)

    def test_bad_or_unknown_tag(self):
        self.assertEqual(self.get('nothex!!').status_code, 400)
        self.assertEqual(self.get('FFFFFFFF').status_code, 404)

    def test_read_only(self):
        before = Transaction.objects.count()
        self.get()
        self.assertEqual(Transaction.objects.count(), before)
        self.assertEqual(APIClient().post('/card_history/ABCD1234/').status_code, 403)
