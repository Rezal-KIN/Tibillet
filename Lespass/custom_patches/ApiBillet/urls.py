from django.urls import include, path
from rest_framework import routers

from ApiBillet import views as api_view
from ApiBillet.views import TicketPdf, Webhook_stripe, Gauge, CancelSubscription
from ApiBillet.cashless_onboarding import OnboardLaboutikMultiCashless, GetUserPubPemMultiCashless

router = routers.DefaultRouter()
router.register(r"here", api_view.HereViewSet, basename="here")
router.register(r"events", api_view.EventsViewSet, basename="event")
router.register(r"eventslug", api_view.EventsSlugViewSet, basename="eventslug")
router.register(r"products", api_view.ProductViewSet, basename="product")
router.register(r"prices", api_view.TarifBilletViewSet, basename="price")
router.register(r"reservations", api_view.ApiReservationViewset, basename="reservation")
router.register(r"optionticket", api_view.OptionTicket, basename="optionticket")
router.register(r"ticket", api_view.TicketViewset, basename="ticket")
router.register(r"wallet", api_view.Wallet, basename="wallet")

urlpatterns = [
    path("", include(router.urls)),
    path("ticket/pdf/<uuid:pk_uuid>", TicketPdf.as_view(), name="ticket_uuid_to_pdf"),
    path("onboard_laboutik/", OnboardLaboutikMultiCashless.as_view()),
    path("get_user_pub_pem/", GetUserPubPemMultiCashless.as_view()),
    path("webhook_stripe/", Webhook_stripe.as_view()),
    path("webhook_stripe/<uuid:uuid_paiement>/", Webhook_stripe.as_view()),
    path("gauge/", Gauge.as_view()),
    path("cancel_sub/", CancelSubscription.as_view()),
]
