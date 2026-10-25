import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Cashless.settings')
django.setup()

from APIcashless.models import Membre, CarteCashless

members = (
    Membre.objects.filter(name__iregex='tabaczka|faure') |
    Membre.objects.filter(prenom__iregex='tabaczka|faure')
).distinct()
print('MEMBRES', members.count())
for m in members:
    print('M', m.id, m.prenom, m.name)
    cards = CarteCashless.objects.filter(membre=m)
    for c in cards:
        print(' C', c.id, c.tag_id, c.number, c.uuid_qrcode)
