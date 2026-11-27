from django.apps import AppConfig


class CardHistoryLaboutikConfig(AppConfig):
    """
    FR : Mode gérant (Gala) : scanner une carte et voir tout son historique.
    Ajoute une route à côté de LaBoutik sans modifier ses fichiers d'URL.
    EN: Manager-mode card history; adds one route without editing LaBoutik URLs.
    """
    name = 'card_history_laboutik'
    verbose_name = 'Historique carte'

    def ready(self):
        from django.urls import path
        from Cashless import urls as root_urls
        from card_history_laboutik.views import card_history

        if not any(getattr(p, 'name', None) == 'gala-card-history' for p in root_urls.urlpatterns):
            # En tête : les motifs natifs `url('wv/')` cherchent aussi en milieu de chemin.
            root_urls.urlpatterns.insert(0, path('gala/card_history/', card_history, name='gala-card-history'))
