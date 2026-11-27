"""Historique d'une carte pour le mode gérant (lecture seule)."""
import logging
import re
from datetime import datetime
from decimal import Decimal

from django.shortcuts import render
from rest_framework.decorators import api_view

logger = logging.getLogger(__name__)
TAG = re.compile(r'^[0-9A-F]{8}$')


def local(value):
    """Heure locale du lieu (fuseau de la configuration LaBoutik)."""
    import pytz
    from APIcashless.models import Configuration
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    zone = pytz.timezone(Configuration.get_solo().fuseau_horaire or 'Europe/Paris')
    # Chaîne déjà formatée : le filtre `date` reconvertirait vers TIME_ZONE (UTC).
    return value.astimezone(zone).strftime('%d/%m %H:%M:%S')


def euros(cents):
    return (Decimal(cents or 0) / 100).quantize(Decimal('0.01'))


def error(request, message, status=200):
    return render(request, 'card_history_laboutik/popup_card_history.html',
                  {'error_msg': message}, status=status)


def manager_allowed(tag_id_cm):
    """La carte primaire mémorisée par la caisse doit avoir le droit au mode gérant."""
    from APIcashless.models import CarteMaitresse
    return bool(tag_id_cm) and CarteMaitresse.objects.filter(
        carte__tag_id=tag_id_cm, edit_mode=True).exists()


def fedow_history(tag_id):
    from APIcashless.models import Configuration
    from fedow_connect.fedow_api import _get
    response = _get(Configuration.get_solo(), path=['card_history', tag_id])
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def till_sales(tag_id):
    from APIcashless.models import ArticleVendu
    sales = (ArticleVendu.objects.filter(carte__tag_id=tag_id)
             .select_related('article', 'pos', 'moyen_paiement', 'responsable')
             .order_by('-date_time')[:200])
    return [{
        'datetime': local(sale.date_time),
        'article': sale.article.name,
        'qty': (sale.qty or Decimal(0)).normalize(),
        'total': ((sale.prix or 0) * (sale.qty or 0)).quantize(Decimal('0.01')),
        'payment': sale.moyen_paiement.name if sale.moyen_paiement_id else '',
        'pos': sale.pos.name if sale.pos_id else '',
        'by': sale.responsable.name if sale.responsable_id else '',
    } for sale in sales]


@api_view(['POST'])
def card_history(request):
    tag_id = (request.data.get('tag_id_client') or '').upper()
    tag_id_cm = (request.data.get('tag_id_cm') or '').upper()
    if not hasattr(request.user, 'appareil') or not manager_allowed(tag_id_cm):
        return error(request, "Historique réservé au mode gérant.", status=403)
    if not TAG.match(tag_id):
        return error(request, "Carte illisible, réessayez.")
    try:
        ledger = fedow_history(tag_id)
    except Exception as exc:
        logger.error(f"card_history Fedow : {type(exc).__name__}")
        return error(request, "Impossible de joindre Fedow. Réessayez.")
    if ledger is None:
        return error(request, "Carte inconnue.")

    for operation in ledger['operations']:
        operation['datetime'] = local(operation['datetime'])
        operation['euros'] = euros(operation['amount'])
    for refill in ledger['online_refills']:
        refill['created_at'] = local(refill['created_at'])
        refill['euros'] = euros(refill['amount'])
        refill['fee_euros'] = euros(refill['fee'])
    for refund in ledger['online_refunds']:
        refund['updated_at'] = local(refund['updated_at'])
        refund['euros'] = euros(refund['amount'])
    balance = sum(b['value'] for b in ledger['balances'] if b['category'] in ('FED', 'TLF', 'TNF'))
    context = {
        'card': ledger['card'],
        'balances': [{**b, 'euros': euros(b['value'])} for b in ledger['balances']],
        'balance': euros(balance),
        'operations': ledger['operations'],
        'truncated': ledger['truncated'],
        'operations_total': ledger['operations_total'],
        'online_refills': ledger['online_refills'],
        'online_refunds': ledger['online_refunds'],
        'sales': till_sales(tag_id),
    }
    return render(request, 'card_history_laboutik/popup_card_history.html', context)
