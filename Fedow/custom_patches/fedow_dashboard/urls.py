from django.urls import path, include
import fedow_dashboard.views as dashboard_views
# from django.conf import settings
from rest_framework import routers

router = routers.DefaultRouter()

urlpatterns = [
    path('gala/create/', dashboard_views.gala_create, name='gala_create'),
    path('active-context/refill_checkout/', dashboard_views.active_context_refill_checkout, name='active_context_refill_checkout'),
    path('active-context/retrieve_refill_checkout/<uuid:pk>/', dashboard_views.active_context_retrieve_refill_checkout, name='active_context_retrieve_refill_checkout'),
    path('guest/refill_checkout/', dashboard_views.guest_refill_checkout, name='guest_refill_checkout'),
    path('guest/retrieve_refill_checkout/<uuid:pk>/', dashboard_views.guest_retrieve_refill_checkout, name='guest_retrieve_refill_checkout'),
    path('active-context/data/', dashboard_views.active_context_data, name='active_context_data'),
    path('active-context/set/', dashboard_views.active_context_set, name='active_context_set'),
    path('suivi/data/', dashboard_views.suivi_data, name='suivi_data'),
    path('suivi/', dashboard_views.suivi, name='suivi'),
    path('place/<uuid:pk>/', dashboard_views.place_view, name='place'),
    path('asset/<uuid:pk>/', dashboard_views.asset_view, name='asset'),
    path('', dashboard_views.index, name='index'),
]
