import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Cashless.settings')
django.setup()

from APIcashless.models import CarteCashless, Assets

tags = ['5481DF65', '54F4E365']

for tag in tags:
    cards = list(CarteCashless.objects.filter(tag_id=tag))
    print('CARD', tag, 'FOUND', len(cards))
    for c in cards:
        deleted_assets, _ = Assets.objects.filter(carte=c).delete()
        print(' ASSETS_DELETED', deleted_assets)
        try:
            c.delete()
            print(' CARD_DELETED', tag)
        except Exception as e:
            print(' CARD_DELETE_ERROR', tag, type(e).__name__, str(e)[:220])

print('REMAINING', list(CarteCashless.objects.filter(tag_id__in=tags).values_list('tag_id', 'number')))
