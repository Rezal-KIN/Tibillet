"""Browser entry to the register, keeping its existing permission checks."""
from urllib.parse import urlencode

from django.core import signing
from django.shortcuts import redirect
from django.urls import reverse


def ouvrir_caisse(request):
    if request.user.is_authenticated:
        return redirect("laboutik-caisse-list")
    # Reuse TiBillet's email login and its signed return destination.
    destination = signing.dumps(reverse("laboutik-caisse-list"))
    return redirect(
        reverse("login-viewset-login-fullpage")
        + "?" + urlencode({"next": destination})
    )
