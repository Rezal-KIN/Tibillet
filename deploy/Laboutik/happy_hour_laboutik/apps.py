from django.apps import AppConfig


class HappyHourLaboutikConfig(AppConfig):
    """
    FR : Happy hour pour le Gala. Ajouté à côté de LaBoutik, sans modifier ses tables :
    un prix happy hour optionnel par article (champ vide = pas de happy hour) et une
    plage horaire quotidienne. Le serveur reste maître du prix.
    EN: Gala happy hour, added next to LaBoutik without altering its tables.
    """
    name = 'happy_hour_laboutik'
    verbose_name = 'Happy hour'

    def ready(self):
        # FR : Le prix happy hour s'édite directement sur la fiche article de l'admin.
        # EN: The happy hour price is edited right on the native article admin page.
        from APIcashless.models import Articles
        from administration.adminstaff import staff_admin_site
        from happy_hour_laboutik.admin import HappyHourPriceInline

        article_admin = staff_admin_site._registry.get(Articles)
        if article_admin and HappyHourPriceInline not in article_admin.inlines:
            article_admin.inlines = [HappyHourPriceInline, *article_admin.inlines]

        # FR : Prix servis aux caisses et contrôle des totaux, sans modifier le code natif.
        # EN: Prices sent to terminals and total checks, without editing native code.
        from webview.serializers import PointDeVenteSerializer
        from webview.validators import DataAchatDepuisClientValidator
        from happy_hour_laboutik.services import install
        install(DataAchatDepuisClientValidator, PointDeVenteSerializer)
