"""The Gala refill setting converges without changing an operator hide flag."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.core.management.base import CommandError

from Administration.management.commands.configure_gala_refill import Command


@pytest.fixture
def gala_config():
    config = SimpleNamespace(
        hide_refill_button=False,
        force_show_refill_button=False,
        show_refill_button=lambda: config.force_show_refill_button,
        save=MagicMock(),
    )
    gala = SimpleNamespace(pk='festival')
    with patch.dict('os.environ', {
        'GALA_APEX_TENANT': '1', 'SUB': 'festival', 'STRIPE_TEST': '1',
        'STRIPE_KEY_TEST': 'sk_test_placeholder',
        'STRIPE_ENDPOINT_SECRET_TEST': 'whsec_placeholder',
    }), patch('Administration.management.commands.configure_gala_refill.Client.objects.get',
              return_value=gala), patch(
        'Administration.management.commands.configure_gala_refill.tenant_context',
        return_value=nullcontext(),
    ), patch('Administration.management.commands.configure_gala_refill.transaction.atomic',
             return_value=nullcontext()), patch(
        'Administration.management.commands.configure_gala_refill.Configuration.get_solo',
        return_value=config,
    ):
        yield config


def test_refill_converges_and_check_does_not_write(gala_config):
    command = Command()
    command.handle(check=False)
    assert gala_config.force_show_refill_button is True
    gala_config.save.assert_called_once_with(update_fields=['force_show_refill_button'])
    command.handle(check=False)
    command.handle(check=True)
    assert gala_config.save.call_count == 1


def test_check_rejects_missing_refill_without_writing(gala_config):
    with pytest.raises(CommandError, match='not visible'):
        Command().handle(check=True)
    gala_config.save.assert_not_called()


def test_operator_hide_is_not_overridden(gala_config):
    gala_config.hide_refill_button = True
    with pytest.raises(CommandError, match='explicitly hidden'):
        Command().handle(check=False)
    gala_config.save.assert_not_called()
