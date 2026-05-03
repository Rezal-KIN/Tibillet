from APIcashless.models import PointDeVente

EMOJI_BY_CAT = {
    'bières': '🍺',
    'cocktails': '🍸',
    'softs': '🥤',
    'vins': '🍷',
}
KNOWN = list(EMOJI_BY_CAT.values())

pdv = PointDeVente.objects.filter(name__iexact="PIAN'S").first()
if not pdv:
    print('PDV_NOT_FOUND')
    raise SystemExit(0)

updated = 0
for art in pdv.articles.filter(archive=False).select_related('categorie').all():
    cat_name = (art.categorie.name if art.categorie else '').strip().lower()
    emoji = EMOJI_BY_CAT.get(cat_name)
    if not emoji:
        continue

    current_name = (art.name or '').strip()
    has_any_emoji = False
    for em in KNOWN:
        if current_name.startswith(em + ' '):
            has_any_emoji = True
            break

    if has_any_emoji:
        base = current_name.split(' ', 1)[1] if ' ' in current_name else current_name
        new_name = f"{emoji} {base}"
    else:
        new_name = f"{emoji} {current_name}"

    if new_name != art.name:
        art.name = new_name
        art.save(update_fields=['name'])
        updated += 1

print('PDV', pdv.name, 'UPDATED', updated)
