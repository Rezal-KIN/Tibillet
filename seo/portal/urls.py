from django.urls import path
from seo.portal.views import CollectiveViewSet

app_name = 'collective'
view = CollectiveViewSet.as_view
urlpatterns = [
    path('connexion/', view({'get': 'begin_login'}), name='login'),
    path('retour/<uuid:ticket_id>/', view({'get': 'login_return'}), name='return'),
    path('session/<uuid:ticket_id>/', view({'get': 'receive'}), name='receive'),
    path('deconnexion/', view({'post': 'leave'}), name='logout'),
    path('lieux/<int:edition_id>/', view({'get': 'enter'}), name='enter'),
    path('administration/', view({'get': 'administration'}), name='administration'),
    path('editions/ajouter/', view({'post': 'register_edition'}), name='register'),
    path('editions/<int:edition_id>/', view({'get': 'edition', 'post': 'edition'}), name='edition'),
    path('administrateurs/', view({'get': 'administrators', 'post': 'administrators'}), name='administrators'),
    path('lots/', view({'get': 'inventory'}), name='inventory'),
    path('cartes-primaires/', view({'get': 'primary_cards', 'post': 'primary_cards'}), name='primary-cards'),
    path('cartes-primaires/<int:primary_id>/', view({'get': 'primary_card', 'post': 'primary_card'}), name='primary-card'),
]
