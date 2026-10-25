import os
import django

# Laboutik
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Cashless.settings')
django.setup()

from APIcashless.models import CarteCashless

tags = ['5481DF65', '54F4E365']

print('LABOUTIK_BEFORE', list(CarteCashless.objects.filter(tag_id__in=tags).values_list('tag_id', 'number')))
for tag in tags:
    qs = CarteCashless.objects.filter(tag_id=tag)
    deleted = 0
    for c in qs:
        c.delete()
        deleted += 1
    print('LABOUTIK_DELETED', tag, deleted)
print('LABOUTIK_AFTER', list(CarteCashless.objects.filter(tag_id__in=tags).values_list('tag_id', 'number')))
