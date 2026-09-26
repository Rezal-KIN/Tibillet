"""No database: guard the idempotent Gala-domain reconciliation contract."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.core.management.base import CommandError

from Administration.management.commands.configure_gala_apex import Command


@pytest.fixture
def domain_objects():
    public = SimpleNamespace(pk='public')
    gala = SimpleNamespace(pk='festival')
    apex = SimpleNamespace(tenant_id='public', tenant=public, is_primary=True, save=MagicMock())
    www = SimpleNamespace(tenant_id='public', tenant=public, is_primary=False, save=MagicMock())
    first = SimpleNamespace(tenant_id='festival', tenant=gala, is_primary=True, save=MagicMock())

    with patch.dict('os.environ', {
        'GALA_APEX_TENANT': '1', 'DOMAIN': 'galas-am-aix.rezal.fr', 'SUB': 'festival',
    }), patch('Administration.management.commands.configure_gala_apex.transaction.atomic',
             return_value=nullcontext()), patch(
        'Administration.management.commands.configure_gala_apex.Client.objects.get',
        side_effect=[public, gala],
    ), patch(
        'Administration.management.commands.configure_gala_apex.Domain.objects.select_for_update',
    ) as domains:
        domains.return_value.get.side_effect = [apex, www, first]
        yield public, gala, apex, www, first


def test_apex_moves_to_gala_and_first_subdomain_becomes_alias(domain_objects):
    _public, gala, apex, www, first = domain_objects
    Command().handle(check=False)
    assert apex.tenant == gala
    assert apex.is_primary is True
    assert www.is_primary is True
    assert first.is_primary is False
    apex.save.assert_called_once_with(update_fields=['tenant', 'is_primary'])


def test_check_refuses_generic_homepage_without_writing(domain_objects):
    _public, _gala, apex, www, first = domain_objects
    with pytest.raises(CommandError, match='does not route'):
        Command().handle(check=True)
    apex.save.assert_not_called()
    www.save.assert_not_called()
    first.save.assert_not_called()


def test_unexpected_apex_owner_is_not_overwritten(domain_objects):
    _public, _gala, apex, _www, _first = domain_objects
    apex.tenant_id = 'other'
    with pytest.raises(CommandError, match='unexpected tenant'):
        Command().handle(check=False)
    apex.save.assert_not_called()
