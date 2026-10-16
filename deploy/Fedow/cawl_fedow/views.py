import logging
import time
from uuid import UUID

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework import serializers
from rest_framework.response import Response

from fedow_core.views import WalletAPI
from fedow_core.serializers import WalletSerializer
from fedow_core.permissions import HasPlaceKeyAndWalletSignature
from payment_providers.cawl import CawlError
from cawl_fedow.models import Checkout, Webhook
from cawl_fedow.services import create_checkout, credit_checkout, gateway

logger = logging.getLogger(__name__)


class AmountInput(serializers.Serializer):
    amount = serializers.IntegerField(min_value=50, max_value=50000)


class RefundInput(serializers.Serializer):
    request_id = serializers.UUIDField()


class CawlWalletAPI(WalletAPI):
    # FR : Les permissions natives contrôlent la clé du lieu et la signature
    # RSA du wallet. Aucune recharge n'est autorisée sur un simple email.
    # EN: Keep the native place key + wallet RSA signature permissions.
    def get_permissions(self):
        if self.action in {"refund_fed_by_signature", "cawl_refund_status"}:
            return [HasPlaceKeyAndWalletSignature()]
        return super().get_permissions()

    def refund_fed_by_signature(self, request):
        from cawl_fedow.refunds import prepare_wallet_refund, refund_summary

        validator = RefundInput(data=request.data)
        validator.is_valid(raise_exception=True)
        try:
            batch, created = prepare_wallet_refund(request, validator.validated_data["request_id"])
        except CawlError as error:
            return Response({"detail": str(error)}, status=409)
        # The durable queue is processed by the runtime timer, outside HTTP and
        # SQLite locks. Returning 202 means recorded, not money received in bank.
        return Response({**refund_summary(batch), "created": created}, status=202)

    def cawl_refund_status(self, request):
        from cawl_fedow.models import WalletRefundRequest
        from cawl_fedow.refunds import refund_summary

        batch = WalletRefundRequest.objects.filter(wallet=request.wallet, place=request.place).order_by("-created_at").first()
        return Response(refund_summary(batch) if batch else {})

    def get_federated_token_refill_checkout(self, request):
        validator = AmountInput(data=request.data)
        validator.is_valid(raise_exception=True)
        try:
            checkout = create_checkout(request, validator.validated_data["amount"])
        except CawlError:
            return Response("Paiement CAWL indisponible.", status=503)
        return Response(checkout.checkout_url, status=202)

    def retrieve_from_refill_checkout(self, request, pk=None):
        checkout = get_object_or_404(Checkout, pk=pk, wallet=request.wallet, place=request.place)
        # FR : Le retour navigateur précède souvent la capture ; on attend un peu,
        # comme le parcours Stripe natif, avant de répondre « en attente ».
        # EN: The browser often returns before capture; wait briefly like native Stripe.
        credited = False
        for attempt in range(4):
            if attempt:
                time.sleep(2)
            try:
                credited = credit_checkout(checkout, request)
            except CawlError:
                return Response("Vérification CAWL impossible.", status=503)
            if credited:
                break
            checkout.refresh_from_db()
        if not credited:
            return Response("Paiement en attente de confirmation.", status=402)
        return Response(WalletSerializer(request.wallet, context={"request": request}).data)


def stripe_disabled(request, **kwargs):
    return HttpResponse("Stripe est désactivé sur cette instance CAWL.", status=410)


@csrf_exempt
@require_POST
def webhook(request):
    if len(request.body) > 256 * 1024:
        return HttpResponse(status=413)
    try:
        client = gateway()
        event = client.verify_webhook(request.body, request.headers)
    except CawlError:
        return HttpResponse(status=400)
    if event["type"].startswith("refund.") and event.get("refund"):
        from cawl_fedow.models import WalletRefund
        from cawl_fedow.refunds import reconcile_wallet_refund, reference

        try:
            if Webhook.objects.filter(event_id=event["id"]).exists():
                return HttpResponse(status=200)
            payload = event["refund"]
            provider_id = payload.get("id")
            if not isinstance(provider_id, str) or not provider_id:
                return HttpResponse(status=400)
            refund = WalletRefund.objects.filter(provider_refund_id=provider_id).select_related("checkout", "request").first()
            if refund is None and reference(payload):
                try:
                    operation_id = UUID(reference(payload))
                except (ValueError, TypeError):
                    operation_id = None
                if operation_id:
                    refund = WalletRefund.objects.filter(pk=operation_id).select_related("checkout", "request").first()
            if refund:
                # Read provider state, not the callback's claimed amount/status.
                reconcile_wallet_refund(refund, submit=False)
            Webhook.objects.get_or_create(event_id=event["id"])
        except Exception:
            logger.error("Webhook de remboursement CAWL non traité, événement %s", event["id"])
            return HttpResponse(status=503)
        return HttpResponse(status=200)
    try:
        with transaction.atomic():
            _, created = Webhook.objects.get_or_create(event_id=event["id"])
            if not created:
                return HttpResponse(status=200)
            payment = event.get("payment")
            if payment and event["type"].startswith("payment."):
                snapshot = client.get_payment(payment["id"])
                try:
                    reference = UUID(snapshot.reference)
                except (ValueError, TypeError):
                    return HttpResponse(status=200)
                checkout = Checkout.objects.filter(
                    pk=reference, merchant_id=client.configuration.merchant_id,
                    test_mode=client.configuration.test_mode,
                ).first()
                if checkout:
                    credit_checkout(checkout, request, snapshot)
    except Exception:
        logger.error("Webhook CAWL Fedow non traité, événement %s", event["id"])
        return HttpResponse(status=503)
    return HttpResponse(status=200)
