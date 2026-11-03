"""Accueil personnalisé et entrée du compte collectif avec connexion native.
/ Branded homepage and collective account entrance using native login.
"""
import re
from urllib.parse import urlencode
from django.conf import settings
from django.core import signing
from django.http import Http404, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


DESTINATIONS = {'compte': '/my_account/', 'solde': '/my_account/balance/'}


def portal_home(request):
    return render(request, 'seo/cashless/landing.html', {
        'page_title': 'Galas Arts et Métiers Aix — Espace cashless',
        'page_description': 'Votre espace cashless : cartes, monnaies et remboursements des Galas.',
        'canonical_url': request.build_absolute_uri('/'),
    })


@require_GET
@never_cache
def portal_space(request):
    if not getattr(settings, 'GALA_CASHLESS_PORTAL', False):
        raise Http404()
    if request.GET.get('section', 'compte') not in DESTINATIONS:
        return HttpResponseBadRequest('Destination inconnue.')
    if request.tenant.schema_name == 'public':
        from seo.portal.views import CollectiveViewSet
        return CollectiveViewSet.as_view({'get': 'space'})(request)
    destination = DESTINATIONS[request.GET.get('section', 'compte')]
    if request.GET.get('retour'):
        try:
            destination = signing.loads(request.GET['retour'], max_age=1800)
        except signing.BadSignature:
            return HttpResponseBadRequest('Retour invalide ou expiré.')
        if not re.fullmatch(r'/collectif/retour/[0-9a-f-]{36}/', destination):
            return HttpResponseBadRequest('Retour invalide.')
    if request.user.is_authenticated:
        return HttpResponseRedirect(destination)
    return HttpResponseRedirect('/login/login_fullpage/?' + urlencode({'next': signing.dumps(destination)}))
