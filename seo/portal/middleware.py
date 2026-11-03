"""Désactivation manuelle et accès à l'assistant réservés au collectif.
/ Manual deactivation and restricted access to the native onboarding wizard.
"""
import re
from django.conf import settings
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.utils.translation import gettext as _


class CollectiveAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, 'GALA_CASHLESS_PORTAL', False):
            from seo.portal.models import GalaEdition
            from seo.portal.services import is_manager
            tenant = getattr(request, 'tenant', None)
            if tenant is not None:
                if request.path.startswith('/onboard/') and not is_manager(request.user):
                    if not request.user.is_authenticated and tenant.schema_name == 'public':
                        return redirect('/collectif/connexion/')
                    return HttpResponseForbidden(_('Création réservée aux gestionnaires du collectif.'))
                if tenant.schema_name != 'public':
                    edition = GalaEdition.objects.filter(venue=tenant, enabled=False).first()
                    if edition:
                        # Le back-office reste ouvert selon les droits natifs.
                        # / Keep administration available under native permissions.
                        safe = request.path.startswith(('/admin/', '/collectif/', '/static/', '/media/'))
                        read_account = request.method == 'GET' and request.path in (
                            '/my_account/', '/my_account/balance/', '/my_account/tokens_table/',
                            '/my_account/transactions_table/', '/espace/', '/login/login_fullpage/')
                        authentication = request.path.startswith('/emailconfirmation/')
                        # Les retours prestataire doivent toujours être rapprochés.
                        # / Provider callbacks must still be reconciled.
                        callback = request.path.startswith(('/api/cawl/', '/fwh/', '/api/webhook_stripe/', '/api/webhook_cawl/'))
                        callback = callback or bool(re.fullmatch(
                            r'/my_account/[0-9a-f-]{36}/return_refill_wallet/', request.path))
                        if not (safe or read_account or authentication or callback):
                            return HttpResponseForbidden(_('Ce lieu a été désactivé par les organisateurs.'))
        return self.get_response(request)
