# AM-Rezal modified version, imported 2026-09-21; source notices updated 2026-10-03.
# Original TiBillet authors retained. GNU AGPLv3: see /LICENSE and /NOTICE.md.
from django.urls import path
import fedow_dashboard.views as dashboard_views
from rest_framework import routers

router = routers.DefaultRouter()

urlpatterns = [
    path('suivi/data/', dashboard_views.suivi_data, name='suivi_data'),
    path('suivi/', dashboard_views.suivi, name='suivi'),
    path('place/<uuid:pk>/', dashboard_views.place_view, name='place'),
    path('asset/<uuid:pk>/', dashboard_views.asset_view, name='asset'),
    path('', dashboard_views.index, name='index'),
]
