from django.urls import path, re_path
from fedowallet_django.urls import urlpatterns as native_urls
from cawl_fedow.views import CawlWalletAPI, stripe_disabled, webhook

urlpatterns = [
    path("webhook_cawl/", webhook, name="cawl-webhook"),
    path("wallet/get_federated_token_refill_checkout/", CawlWalletAPI.as_view({"post": "get_federated_token_refill_checkout"})),
    path("wallet/<uuid:pk>/retrieve_from_refill_checkout/", CawlWalletAPI.as_view({"get": "retrieve_from_refill_checkout"})),
    path("wallet/global_asset_bank_stripe_deposit/", stripe_disabled),
    path("wallet/refund_fed_by_signature/", stripe_disabled),
    path("webhook_stripe/", stripe_disabled),
    re_path(r"^stripe(?:/|$)", stripe_disabled),
] + native_urls
