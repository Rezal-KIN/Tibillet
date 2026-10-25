from decimal import Decimal
import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Cashless.settings')
django.setup()

from APIcashless.models import PointDeVente, Categorie, Articles, Methode

pdv, _ = PointDeVente.objects.get_or_create(
    name='shots',
    defaults={
        'comportement': 'A',
        'accepte_especes': True,
        'accepte_carte_bancaire': True,
        'accepte_commandes': False,
    }
)

if pdv.comportement != 'A':
    pdv.comportement = 'A'
    pdv.save(update_fields=['comportement'])

vente, _ = Methode.objects.get_or_create(name='VenteArticle')

cats = {}
for name, icon, order in [
    ('Shots', 'fa-glass-cheers', 1),
    ('Softs', 'fa-glass-water', 2),
]:
    cat, _ = Categorie.objects.get_or_create(name=name, defaults={'icon': icon, 'poid_liste': order})
    changed = False
    if not cat.icon:
        cat.icon = icon
        changed = True
    if cat.poid_liste != order:
        cat.poid_liste = order
        changed = True
    if changed:
        cat.save(update_fields=['icon', 'poid_liste'])
    cats[name] = cat

rows = [
    ('Shots', '🥃 Shot x1', '2.00', 1),
    ('Shots', '🥃 Shot x2', '3.50', 2),
    ('Shots', '🥃 Shot x6', '10.00', 3),
    ('Shots', '🥃 Shot x10', '15.00', 4),
    ('Softs', '🥤 Eau 50cl', '1.00', 101),
    ('Softs', '🥤 Coca-Cola 33cl', '2.00', 102),
    ('Softs', '🥤 Coca-Cola Zéro 33cl', '2.00', 103),
    ('Softs', '🥤 Fuze Tea 33cl', '2.00', 104),
    ('Softs', '🥤 Orangina 33cl', '2.00', 105),
    ('Softs', '🥤 Red Bull 25cl', '2.50', 106),
]

created = 0
updated = 0
for cat_name, art_name, prix, order in rows:
    art, was_created = Articles.objects.get_or_create(
        name=art_name,
        defaults={
            'prix': Decimal(prix),
            'prix_achat': Decimal('0.00'),
            'categorie': cats[cat_name],
            'methode': vente,
            'methode_choices': Articles.VENTE,
            'archive': False,
            'poid_liste': order,
        }
    )

    if was_created:
        created += 1
    else:
        changed = False
        if art.prix != Decimal(prix):
            art.prix = Decimal(prix)
            changed = True
        if art.categorie_id != cats[cat_name].id:
            art.categorie = cats[cat_name]
            changed = True
        if art.methode_id != vente.id:
            art.methode = vente
            changed = True
        if art.methode_choices != Articles.VENTE:
            art.methode_choices = Articles.VENTE
            changed = True
        if art.archive:
            art.archive = False
            changed = True
        if art.poid_liste != order:
            art.poid_liste = order
            changed = True
        if changed:
            art.save()
            updated += 1

    pdv.articles.add(art)

print('PDV', pdv.id, pdv.name)
print('CREATED', created, 'UPDATED', updated, 'TOTAL_LINKED', pdv.articles.filter(archive=False).count())
for a in pdv.articles.filter(archive=False).select_related('categorie').order_by('categorie__poid_liste', 'poid_liste', 'name'):
    print(f"- {a.categorie.name} | {a.name} | {a.prix}")
