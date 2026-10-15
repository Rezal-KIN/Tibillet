"""Opt-in QR onboarding through real Smoke Lespass and Fedow, without payment.

Run only on Smoke with ``RUN_QR_CARD_E2E=1``. The guards below prevent a real
SMTP message or live Stripe mode even if invoked from another environment.
"""

import os
from urllib.parse import urlparse
from uuid import UUID, uuid4

import pytest
from django.conf import settings
from django.test import Client as DjangoClient
from django_tenants.utils import tenant_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import Configuration
from Customers.models import Client
from fedow_connect.fedow_api import FedowAPI


pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_new_qr_card_links_and_opens_refill_landing():
    if os.environ.get('RUN_QR_CARD_E2E') != '1':
        pytest.skip('explicit Smoke E2E opt-in required')
    provider = os.environ.get('PAYMENT_PROVIDER', 'stripe')
    test_mode = (provider == 'stripe' and os.environ.get('STRIPE_TEST') == '1'
                 or provider == 'cawl' and os.environ.get('CAWL_TEST') == '1')
    # The wrapper uses memory mail for this synthetic journey. Real mail
    # delivery is checked separately against the configured test mailbox.
    if not (test_mode
            and os.environ.get('GALA_APEX_TENANT') == '1'
            and os.environ.get('EMAIL_BACKEND') in {
                'django.core.mail.backends.dummy.EmailBackend',
                'django.core.mail.backends.locmem.EmailBackend',
            }
            and settings.EMAIL_BACKEND in {
                'django.core.mail.backends.dummy.EmailBackend',
                'django.core.mail.backends.locmem.EmailBackend',
            }):
        pytest.skip('requires Smoke payment test mode and non-SMTP mail backend')

    domain = os.environ['DOMAIN']
    tenant = Client.objects.get(schema_name=os.environ['SUB'])
    # Prepared through Laboutik, which alone can sign card creation after its
    # RSA key has been paired with Fedow. See run-qr-smoke-e2e.sh.
    if not os.environ.get('QR_SMOKE_CARD_UUID') or not os.environ.get('QR_SMOKE_CARD_NUMBER'):
        pytest.skip('run via versioned run-qr-smoke-e2e.sh')
    card_id = UUID(os.environ['QR_SMOKE_CARD_UUID'])
    card_number = os.environ['QR_SMOKE_CARD_NUMBER']
    email = f'qr-smoke-{uuid4().hex[:12]}@example.org'
    user = None

    with tenant_context(tenant):
        api = FedowAPI()
        assert api.NFCcard.qr_retrieve(card_id)['is_wallet_ephemere'] is True

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

        # The deployment must enable the real setting; do not mock the CTA.
        with tenant_context(tenant):
            assert Configuration.get_solo().show_refill_button() is True
        landing = browser.get(f'/qr/{card_id}/')
        assert landing.status_code == 200
        assert b'/my_account/refill_wallet/' in landing.content

        # Only the provider checkout differs; native onboarding is shared.
        checkout = browser.get('/my_account/refill_wallet/', HTTP_HX_REQUEST='true')
        assert checkout.status_code == 200
        if provider == 'stripe':
            checkout_url = urlparse(checkout['HX-Redirect'])
            assert (checkout_url.scheme, checkout_url.hostname) == ('https', 'checkout.stripe.com')
        else:
            assert checkout['HX-Redirect'] == '/my_account/refill_wallet/'
            amount_form = browser.get('/my_account/refill_wallet/')
            assert amount_form.status_code == 200
            assert b'name="amount"' in amount_form.content
            checkout = browser.post('/my_account/refill_wallet/', {'amount': 100})
            assert checkout.status_code == 302
            checkout_url = urlparse(checkout['Location'])
            assert (checkout_url.scheme, checkout_url.hostname) == ('https', 'payment.preprod.cawl-solutions.fr')
    finally:
        if user is not None:
            with tenant_context(tenant):
                FedowAPI().NFCcard.lost_my_card_by_signature(
                    user, number_printed=card_number,
                )
