"""Run with Fedow manage.py shell; only update the selected place's domain."""
import json
import os
from uuid import UUID

from django.db import transaction
from fedow_core.models import Place

mode = os.environ.get('ESTIA_DOMAIN_MODE', 'plan')
if mode not in ('plan', 'apply', 'rollback'):
    raise RuntimeError('Mode attendu : plan, apply ou rollback')
place_uuid = UUID(os.environ['ESTIA_PLACE_UUID'])
old = 'lespass.tibillet.localhost'
public = 'cashless.gala-test.rezal.fr'
with transaction.atomic():
    places = Place.objects.all()
    if mode != 'plan':
        places = places.select_for_update()
    place = places.get(uuid=place_uuid)
    if place.lespass_domain not in (old, public):
        raise RuntimeError('Domaine inattendu pour la place Fedow selectionnee')
    print(json.dumps({'mode': mode, 'place': str(place_uuid),
                      'avant': place.lespass_domain, 'cible': public}))
    if mode != 'plan':
        target = public if mode == 'apply' else old
        places.filter(uuid=place_uuid).update(lespass_domain=target)
        print('Seul lespass_domain mis a jour ; cles et portefeuilles inchanges.')
