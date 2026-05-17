import logging
from decimal import Decimal
from django.http import JsonResponse, HttpResponse
from fedow_connect.fedow_api import FedowAPI

logger = logging.getLogger(__name__)

EXCLUDE_CATS = ('SUB', 'BDG')


def _cents_to_eur(val):
    if isinstance(val, int):
        return Decimal(val) / 100
    return Decimal(str(val))


def _get_tokens(request):
    fedowAPI = FedowAPI()
    wallet = fedowAPI.wallet.cached_retrieve_by_signature(request.user).validated_data
    return [t for t in wallet.get('tokens', [])
            if (t.get('asset_category') or t.get('asset', {}).get('category', '')) not in EXCLUDE_CATS]


def balance_total(request):
    if not request.user.is_authenticated:
        return JsonResponse({'total': 0}, status=401)
    try:
        tokens = _get_tokens(request)
        total = sum(_cents_to_eur(t.get('value', 0)) for t in tokens)
        return JsonResponse({'total': float(round(total, 2))})
    except Exception as e:
        logger.error(f"balance_total error: {e}")
        return JsonResponse({'total': 0, 'error': str(e)}, status=500)


def balance_tokens_rows(request):
    """Retourne les lignes HTML de solde par monnaie pour injection dans le tableau tirelire."""
    if not request.user.is_authenticated:
        return HttpResponse('')
    try:
        tokens = _get_tokens(request)
        rows = []
        for token in tokens:
            val = _cents_to_eur(token.get('value', 0))
            if val <= 0:
                continue
            asset = token.get('asset', {})
            is_primary = asset.get('is_stripe_primary', False)
            name = 'Monnaie intergala (TiBillets)' if is_primary else token.get('name', asset.get('name', '?'))
            rows.append(
                f'<tr>'
                f'<td><span class="badge bg-success">Solde actuel</span></td>'
                f'<td>{name}</td>'
                f'<td><strong>{val:.2f} €</strong></td>'
                f'<td>—</td>'
                f'</tr>'
            )
        return HttpResponse(''.join(rows))
    except Exception as e:
        logger.error(f"balance_tokens_rows error: {e}")
        return HttpResponse('')
