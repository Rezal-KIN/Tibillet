import logging
from uuid import UUID

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from payment_providers.cawl import CawlError
from PaiementCawl.services import enabled, gateway, rapprocher_le_remboursement

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def webhook(request):
    """
    Webhook CAWL d'un lieu : `https://<domaine du lieu>/api/webhook_cawl/`.
    / CAWL webhook of a venue.

    LOCALISATION : PaiementCawl/views.py

    La signature est vérifiée avec la clé de l'instance, et le lieu doit être dans
    `CAWL_TENANT_SCHEMAS` (`gateway()`). Le paiement n'est cherché que dans le schéma
    du domaine appelé. Son état est relu chez CAWL par `update_checkout_status`, le
    même chemin que le retour navigateur : le contenu du webhook ne fait jamais foi.
    / Signature checked with the instance key; the venue must be allowed. The payment
    is only looked up in the called domain's schema, and its state read again at CAWL.

    Un échec de traitement renvoie 503 sans enregistrer l'événement : CAWL le relivre.
    Un événement déjà traité est acquitté sans rien refaire.
    / A processing failure returns 503 without recording the event: CAWL redelivers.
    """
    from BaseBillet.models import Paiement_stripe
    from PaiementCawl.models import CawlPayment, CawlRefund, CawlWebhook

    if not enabled():
        return HttpResponse(status=404)
    if len(request.body) > 256 * 1024:
        return HttpResponse(status=413)
    try:
        client = gateway()
        event = client.verify_webhook(request.body, request.headers)
    except CawlError:
        return HttpResponse(status=400)

    # Pas de transaction englobante : `update_checkout_status` enregistre le paiement
    # hors transaction, comme le chemin Stripe (tâches Celery des déclencheurs).
    # L'événement n'est enregistré qu'APRÈS un traitement réussi ; deux livraisons
    # simultanées sont départagées par la réservation du paiement.
    # / No enclosing transaction (the payment is saved outside one, like Stripe). The
    # event is recorded only AFTER success; concurrent deliveries meet the claim.
    if CawlWebhook.objects.filter(event_id=event["id"]).exists():
        return HttpResponse(status=200)
    try:
        payment_object = event.get("payment")
        if payment_object and event["type"].startswith("payment."):
            snapshot = client.get_payment(payment_object["id"])
            try:
                reference = UUID(snapshot.reference)
            except (ValueError, TypeError):
                return HttpResponse(status=200)
            record = CawlPayment.objects.filter(
                payment_id=reference, merchant_id=client.configuration.merchant_id,
                test_mode=client.configuration.test_mode,
            ).first()
            if record:
                paiement = Paiement_stripe.objects.get(pk=record.payment_id)
                paiement.update_checkout_status()

        if event.get("refund"):
            remboursement = CawlRefund.objects.filter(
                provider_refund_id=event["refund"].get("id"),
            ).select_related("payment").first()
            if remboursement:
                rapprocher_le_remboursement(remboursement)
        CawlWebhook.objects.get_or_create(event_id=event["id"], defaults={"event_type": event["type"]})
    except Exception:
        logger.error("Traitement du webhook CAWL impossible, événement %s", event.get("id"))
        return HttpResponse(status=503)
    return HttpResponse(status=200)
