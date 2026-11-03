"""Ajouter une route d'inventaire en lecture seule à l'image Fedow épinglée.
/ Add one authenticated read-only inventory route to the pinned Fedow image.
"""
from pathlib import Path

path = Path('/home/fedow/Fedow/fedowallet_django/urls.py')
source = path.read_text()
anchor = 'urlpatterns = ['
if source.count(anchor) != 1:
    raise ValueError('Native Fedow URL configuration changed; refusing to patch.')
source = source.replace(anchor, "from fedow_core.collective_inventory import CollectiveInventory\n\n" + anchor +
                        "\n    path('collective/inventory/', CollectiveInventory.as_view({'get': 'list'})),", 1)
path.write_text(source)
