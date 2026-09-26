"""Transport selection for inactive Galas sharing the public DNS names."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fedow_connect.fedow_api import _fedow_base_url, _get


def _config():
    return SimpleNamespace(
        fedow_domain=lambda: 'fedow.galas-am-aix.rezal.fr',
        get_fedow_place_admin_apikey=lambda: 'test-only-api-key',
    )


def test_gala_uses_only_fixed_local_fedow_service():
    config = _config()
    with patch.dict('os.environ', {'GALA_LOCAL_FEDOW': '1'}), patch(
        'fedow_connect.fedow_api.requests.Session',
    ) as session_class:
        session_class.return_value.get.return_value = MagicMock(status_code=200)
        _get(config, path='helloworld')
        args, kwargs = session_class.return_value.get.call_args
    assert args[0] == 'http://fedow_nginx/helloworld/'
    assert kwargs['headers']['Host'] == 'fedow.galas-am-aix.rezal.fr'


def test_other_installations_keep_public_https():
    config = _config()
    with patch.dict('os.environ', {'GALA_LOCAL_FEDOW': '0'}):
        assert _fedow_base_url(config) == 'https://fedow.galas-am-aix.rezal.fr'
