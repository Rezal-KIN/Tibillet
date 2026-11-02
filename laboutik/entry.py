"""Browser entry to the register, keeping its existing permission checks."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


@login_required(login_url="/admin/login/")
def ouvrir_caisse(request):
    return redirect("laboutik-caisse-list")
