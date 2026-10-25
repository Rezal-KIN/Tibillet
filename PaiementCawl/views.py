import logging
from uuid import UUID

from django.db import transaction
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from payment_providers.cawl import CawlError
from PaiementCawl.services import enabled, gateway, update_payment

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def webhook(request):
    from PaiementCawl.models import CawlPayment, CawlWebhook

    if not enabled():
        return HttpResponse(status=404)
    if len(request.body) > 256 * 1024:
        return HttpResponse(status=413)
    try:
        client = gateway()
        event = client.verify_webhook(request.body, request.headers)
    except CawlError:
        return HttpResponse(status=400)
    try:
        with transaction.atomic():
            _, created = CawlWebhook.objects.get_or_create(
                event_id=event["id"], defaults={"event_type": event["type"]},
            )
            if not created:
                return HttpResponse(status=200)
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
                ).select_related("payment").first()
                if record:
                    update_payment(record.payment, snapshot)
            if event.get("refund"):
                from PaiementCawl.models import CawlRefund
                from PaiementCawl.refunds import reconcile_refund
                refund = CawlRefund.objects.filter(provider_refund_id=event["refund"]["id"]).select_related("payment").first()
                if refund:
                    reconcile_refund(refund)
    except Exception:
        # FR : Le rollback permet à CAWL de relivrer un événement non traité.
        # EN: Do not acknowledge failed processing; rollback enables redelivery.
        logger.error("Traitement du webhook CAWL impossible, événement %s", event["id"])
        return HttpResponse(status=503)
    return HttpResponse(status=200)
