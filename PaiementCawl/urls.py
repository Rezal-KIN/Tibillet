from django.urls import path
from PaiementCawl.views import webhook

urlpatterns = [path("webhook_cawl/", webhook, name="cawl-webhook")]
