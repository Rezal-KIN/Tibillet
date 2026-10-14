import logging
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
from payment_providers.cawl import CawlError
from cawl_fedow.models import Checkout, Webhook
from cawl_fedow.services import create_checkout, credit_checkout, gateway

logger = logging.getLogger(__name__)


class AmountInput(serializers.Serializer):
    amount = serializers.IntegerField(min_value=50, max_value=50000)


class CawlWalletAPI(WalletAPI):
    # FR : Les permissions natives contrôlent la clé du lieu et la signature
    # RSA du wallet. Aucune recharge n'est autorisée sur un simple email.
    # EN: Keep the native place key + wallet RSA signature permissions.
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
        try:
            credited = credit_checkout(checkout, request)
        except CawlError:
            return Response("Vérification CAWL impossible.", status=503)
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
