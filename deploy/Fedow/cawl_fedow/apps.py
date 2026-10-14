from django.apps import AppConfig


class CawlFedowConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cawl_fedow"

    def ready(self):
        from django.conf import settings
        if getattr(settings, "PAYMENT_PROVIDER", "stripe") == "cawl":
            from fedow_core.models import Configuration

            def stripe_disabled(configuration):
                # FR : L'image conserve ses commandes historiques ; aucune ne
                # doit récupérer une clé Stripe après la bascule CAWL.
                # EN: Block legacy key access without deleting historical secrets.
                raise ValueError("Stripe est désactivé : PAYMENT_PROVIDER=cawl.")

            Configuration.get_stripe_api = stripe_disabled
            Configuration.get_stripe_endpoint_secret = stripe_disabled
