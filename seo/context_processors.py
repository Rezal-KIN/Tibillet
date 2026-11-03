"""Identité du portail activée explicitement ; les lieux gardent leur skin.
/ Explicitly enabled portal branding; venue skins remain native.
"""
from django.conf import settings


def root_portal(request):
    enabled = getattr(settings, "GALA_CASHLESS_PORTAL", False)
    gala_date = None
    tenant = getattr(request, 'tenant', None)
    if enabled and tenant is not None and tenant.schema_name != 'public':
        from seo.portal.models import GalaEdition
        gala_date = GalaEdition.objects.filter(venue=tenant).values_list('gala_date', flat=True).first()
    return {"cashless_gala_date": gala_date, "cashless_portal_enabled": enabled,
            "root_base_template": "seo/cashless/base.html" if enabled else "seo/base_default.html"}
