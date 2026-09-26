"""QR onboarding regression tests; no Fedow, SMTP or database calls."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from django.test import RequestFactory

from BaseBillet.views_qr_card import qr_card_landing, qr_card_link


@pytest.fixture(autouse=True)
def _allow_mock_host(settings):
    settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, 'gala.example']


def _request(method, path, data=None, authenticated=False):
    factory = RequestFactory()
    request = getattr(factory, method)(path, data=data or {}, HTTP_HOST='gala.example')
    request.user = SimpleNamespace(is_authenticated=authenticated, pk=uuid4())
    return request


def _form(card_id, email='person@example.org'):
    return {
        'qrcode_uuid': str(card_id),
        'email': email,
        'emailConfirmation': email,
        'cgu': 'on',
        'firstname': 'Ada',
        'lastname': 'Lovelace',
    }


@patch('BaseBillet.views_qr_card.messages.error')
@patch('BaseBillet.views_qr_card.login')
@patch('BaseBillet.views_qr_card._send_magic_link')
@patch('BaseBillet.views_qr_card._link_card', return_value=True)
@patch('BaseBillet.views_qr_card.get_or_create_user')
@patch('BaseBillet.views_qr_card._card', return_value=({'is_wallet_ephemere': True}, 'gala.example'))
def test_new_email_links_and_enters_without_email_click(_card, get_user, link, send_magic, login, _messages):
    card_id = uuid4()
    user = SimpleNamespace(first_name='', last_name='', accept_newsletter=False,
                           is_active=False, email_valid=False, save=MagicMock())
    get_user.return_value = (user, True)
    response = qr_card_link(_request('post', '/qr/link/', _form(card_id)))
    assert response.status_code == 200
    assert response['HX-Redirect'] == f'/qr/{card_id}/'
    link.assert_called_once_with(user, card_id)
    login.assert_called_once()
    send_magic.assert_called_once_with(user, card_id)
    assert user.email_valid is False  # verification email remains a separate step


@patch('BaseBillet.views_qr_card.messages.error')
@patch('BaseBillet.views_qr_card.login')
@patch('BaseBillet.views_qr_card._link_card')
@patch('BaseBillet.views_qr_card._send_magic_link')
@patch('BaseBillet.views_qr_card.get_or_create_user')
@patch('BaseBillet.views_qr_card._card', return_value=({'is_wallet_ephemere': True}, 'gala.example'))
def test_existing_email_requires_magic_link(_card, get_user, send_magic, link, login, _messages):
    card_id = uuid4()
    get_user.return_value = (MagicMock(), False)
    response = qr_card_link(_request('post', '/qr/link/', _form(card_id)))
    assert response['HX-Redirect'] == f'/qr/check-email/{card_id}/'
    link.assert_not_called()
    login.assert_not_called()
    send_magic.assert_called_once()


@patch('BaseBillet.views_qr_card.render')
@patch('BaseBillet.views_qr_card._context', return_value={})
@patch('BaseBillet.views_qr_card._send_magic_link')
@patch('BaseBillet.views_qr_card.Wallet.objects.get')
@patch('BaseBillet.views_qr_card._card', return_value=({'is_wallet_ephemere': False, 'wallet_uuid': uuid4()}, 'gala.example'))
def test_linked_card_sends_magic_without_logging_in(_card, wallet_get, send_magic, _context, render):
    owner = SimpleNamespace(pk=uuid4(), email='owner@example.org')
    wallet_get.return_value.user = owner
    render.return_value = SimpleNamespace(status_code=200)
    response = qr_card_landing(_request('get', '/qr/card/'), uuid4())
    assert response.status_code == 200
    send_magic.assert_called_once()
    assert render.call_args.args[1] == 'reunion/views/qr_check_email.html'


@patch('BaseBillet.views_qr_card._send_magic_link')
@patch('BaseBillet.views_qr_card.Wallet.objects.get')
@patch('BaseBillet.views_qr_card._card', return_value=({'is_wallet_ephemere': False, 'wallet_uuid': uuid4()}, 'gala.example'))
def test_linked_card_rejects_different_authenticated_user(_card, wallet_get, send_magic):
    wallet_get.return_value.user = SimpleNamespace(pk=uuid4())
    response = qr_card_landing(_request('get', '/qr/card/', authenticated=True), uuid4())
    assert response.status_code == 403
    send_magic.assert_not_called()
