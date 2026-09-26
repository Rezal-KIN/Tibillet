"""Opt-in QR onboarding through real Smoke Lespass and Fedow, without payment.

Run only on Smoke with ``RUN_QR_CARD_E2E=1``. The guards below prevent a real
SMTP message or live Stripe mode even if invoked from another environment.
"""

import os
import secrets
from uuid import uuid4

import pytest
from django.conf import settings
from django.test import Client as DjangoClient
from django_tenants.utils import tenant_context

from AuthBillet.models import TibilletUser
from Customers.models import Client
from fedow_connect.fedow_api import FedowAPI


pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_new_qr_card_links_and_opens_refill_landing():
    if os.environ.get('RUN_QR_CARD_E2E') != '1':
        pytest.skip('explicit Smoke E2E opt-in required')
    # Django's test runner replaces the runtime dummy backend with its own
    # in-memory backend. Check both the deployed configuration and the backend
    # actually used by this test so a real SMTP send can never slip through.
    if not (os.environ.get('STRIPE_TEST') == '1'
            and os.environ.get('GALA_APEX_TENANT') == '1'
            and os.environ.get('EMAIL_BACKEND') == 'django.core.mail.backends.dummy.EmailBackend'
            and settings.EMAIL_BACKEND in {
                'django.core.mail.backends.dummy.EmailBackend',
                'django.core.mail.backends.locmem.EmailBackend',
            }):
        pytest.skip('requires Smoke Stripe test mode and non-SMTP mail backend')

    domain = os.environ['DOMAIN']
    tenant = Client.objects.get(schema_name=os.environ['SUB'])
    card_id = uuid4()
    card_number = secrets.token_hex(4).upper()
    email = f'qr-smoke-{uuid4().hex[:12]}@example.org'
    user = None

    with tenant_context(tenant):
        api = FedowAPI()
        assert api.NFCcard.create_cards([{
            'first_tag_id': secrets.token_hex(4).upper(),
            'complete_tag_id_uuid': str(uuid4()),
            'qrcode_uuid': str(card_id),
            'number_printed': card_number,
            'generation': 1,
            'is_primary': False,
        }])

    try:
        browser = DjangoClient(HTTP_HOST=domain)
        first = browser.get(f'/qr/{card_id}/')
        assert first.status_code == 200
        assert b'qrcode_uuid' in first.content

        linked = browser.post('/qr/link/', data={
            'qrcode_uuid': str(card_id),
            'email': email,
            'emailConfirmation': email,
            'firstname': 'QR',
            'lastname': 'Smoke',
            'cgu': 'on',
        }, HTTP_HX_REQUEST='true')
        assert linked.status_code == 200
        assert linked['HX-Redirect'] == f'/qr/{card_id}/'

        with tenant_context(tenant):
            user = TibilletUser.objects.get(email=email)
            assert user.is_active is True
            assert user.email_valid is False
            assert FedowAPI().NFCcard.qr_retrieve(card_id)['is_wallet_ephemere'] is False

        landing = browser.get(f'/qr/{card_id}/')
        assert landing.status_code == 200
        assert b'/my_account/refill_wallet/' in landing.content
    finally:
        if user is not None:
            with tenant_context(tenant):
                FedowAPI().NFCcard.lost_my_card_by_signature(
                    user, number_printed=card_number,
                )
