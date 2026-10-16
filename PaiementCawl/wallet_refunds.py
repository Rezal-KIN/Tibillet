"""Account UI for the signed Fedow refund queue. Money remains in Fedow."""

import logging
from decimal import Decimal
from uuid import UUID

from django.contrib import messages
from django.core.cache import cache
from django.http import HttpResponseRedirect
from django_htmx.http import HttpResponseClientRedirect

from BaseBillet.tasks import send_email_generique
from fedow_connect.fedow_api import FedowAPI

logger = logging.getLogger(__name__)


def status_context(user):
    try:
        result = FedowAPI().wallet.cawl_wallet_refund_status(user)
        for key in ("amount", "refunded", "released", "pending"):
            if key in result:
                result[key + "_eur"] = Decimal(result[key]) / 100
        if result.get('released'):
            cache.delete(f"wallet_user_{user.wallet.uuid}")
        return result
    except Exception:
        logger.warning("Suivi du remboursement CAWL indisponible")
        return {"unavailable": True}


def request_wallet_refund(request):
    redirect = HttpResponseClientRedirect if request.headers.get('HX-Request') else HttpResponseRedirect
    destination = '/my_account/balance/'
    if request.method != 'POST':
        return redirect(destination)
    if not request.user.email_valid:
        messages.warning(request, "Validez votre adresse email avant de demander un remboursement.")
        return redirect(destination)
    try:
        request_id = UUID(request.POST.get('request_id', ''))
    except (TypeError, ValueError, AttributeError):
        messages.error(request, "La demande est invalide. Rechargez la page avant de réessayer.")
        return redirect(destination)
    try:
        status, result = FedowAPI().wallet.request_cawl_wallet_refund(request.user, request_id)
    except Exception:
        # A timeout does not tell us whether Fedow reserved the balance. Reusing
        # the form's UUID is safe; a fresh independent request is not a retry.
        logger.warning("Réponse de la demande de remboursement CAWL non confirmée")
        messages.warning(request, "La réponse a été interrompue. Consultez le suivi du remboursement avant de réessayer.")
        return redirect(destination)
    if status != 202:
        messages.warning(request, result.get('detail', "La demande n'a pas pu être enregistrée. Contactez le collectif."))
        return redirect(destination)
    cache.delete(f"wallet_user_{request.user.wallet.uuid}")
    if result['status'] == 'EMPTY':
        messages.info(request, "Votre solde rechargeable en ligne est déjà vide.")
    else:
        messages.info(request, "Votre demande de remboursement est enregistrée. Son état est affiché ci-dessous.")
    if result.get('created') and result['amount'] > 0:
        amount = f"{Decimal(result['amount']) / 100:.2f}"
        context = {
            'username': request.user.full_name() or request.user.email,
            'title': f"Demande de remboursement de {amount} € enregistrée",
            'sub_title': "TiBillet",
            'main_text': f"Votre demande de remboursement de {amount} € a été enregistrée pour traitement auprès de CAWL.",
            'main_text_2': "Ce montant est retiré du solde disponible pendant le traitement. Vous pouvez suivre la demande dans votre espace Mon solde. En cas de refus bancaire définitif, le montant est recrédité sur votre portefeuille.",
            'table_info': {'Montant demandé': f'{amount} €', 'Référence': str(request_id)},
            'end_text': "Le remboursement est destiné aux moyens de paiement des recharges d'origine.",
            'signature': "TiBillet",
        }
        try:
            send_email_generique.delay(context=context, email=request.user.email)
        except Exception:
            logger.warning("Notification du remboursement CAWL non envoyée, demande %s", request_id)
    return redirect(destination)
