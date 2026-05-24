from django.urls import path, include
from rest_framework import routers
from BaseBillet import views as base_view
from BaseBillet.views_robots import robots_txt
from BaseBillet.test_error_views import test_404, test_500
import BaseBillet.views_scan as views_scan
from BaseBillet.views_balance_total import balance_total, balance_tokens_rows, refund_local_form, refund_local_success

router = routers.DefaultRouter()
router.register(r'memberships', base_view.MembershipMVT, basename='membership_mvt')
router.register(r'badge', base_view.Badge, basename='badge')
router.register(r'tenant', base_view.Tenant, basename='tenant')
router.register(r'federation', base_view.FederationViewset, basename='federation')

router.register(r'my_account', base_view.MyAccount, basename='my_account')
router.register(r'qrcodescanpay', base_view.QrCodeScanPay, basename='qrcodescanpay')
router.register(r'qr', base_view.ScanQrCode, basename='scan_qrcode')
router.register(r'event', base_view.EventMVT, basename='event')
router.register(r'home', base_view.HomeViewset, basename='home')
router.register(r'login', base_view.TiBilletLogin, basename='login-viewset')
router.register(r'specialadminaction', base_view.SpecialAdminAction, basename='specialadminaction')

urlpatterns = [
    path('robots.txt', robots_txt, name='robots_txt'),

    ### SCAN TICKET API
    path('scan/check_api_scan/', views_scan.check_api_scan.as_view(), name='check_api_scan'),
    path('scan/check_allow_any/', views_scan.check_allow_any.as_view(), name='check_allow_any'),
    path('scan/check_allow_any_widlcard/', views_scan.check_allow_any_widlcard.as_view(),
         name='check_allow_any_widlcard'),
    path('scan/<str:pk>/pair/', views_scan.Pair.as_view(), name='check_api_scan'),
    path('scan/check_ticket/', views_scan.check_ticket.as_view(), name='check_ticket'),
    path('scan/ticket/', views_scan.ticket.as_view(), name='ticket'),
    path('scan/search_ticket/', views_scan.search_ticket.as_view(), name='search_ticket'),
    path('scan/list_tickets/', views_scan.list_tickets.as_view(), name='list_tickets'),

    path('test-errors/404/', test_404, name='test_404'),
    path('test-errors/500/', test_500, name='test_500'),

    path('ticket/<uuid:pk_uuid>/', base_view.Ticket_html_view.as_view()),

    path('connexion/', base_view.connexion, name='connexion'),
    path('deconnexion/', base_view.deconnexion, name='deconnexion'),
    path('emailconfirmation/<str:token>', base_view.emailconfirmation, name='emailconfirmation'),
    path('infos-pratiques/', base_view.infos_pratiques, name='infos_pratiques'),

    path('', base_view.index, name="index"),
    path('my_account/balance_total/', balance_total, name='balance_total'),
    path('my_account/balance_tokens_rows/', balance_tokens_rows, name='balance_tokens_rows'),
    path('my_account/refund_local_form/', refund_local_form, name='refund_local_form'),
    path('my_account/refund_local_success/', refund_local_success, name='refund_local_success'),
]

urlpatterns += router.urls
