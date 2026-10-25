from decimal import Decimal
import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Cashless.settings')
django.setup()

from APIcashless.models import PointDeVente, Categorie, Articles, Methode

pdv, _ = PointDeVente.objects.get_or_create(
    name="oenol'ss",
    defaults={
        'comportement': 'A',
        'accepte_especes': True,
        'accepte_carte_bancaire': True,
        'accepte_commandes': False,
    }
)

# Ensure standard behavior
changed_pdv = False
if pdv.comportement != 'A':
    pdv.comportement = 'A'
    changed_pdv = True
if changed_pdv:
    pdv.save()

vente, _ = Methode.objects.get_or_create(name='VenteArticle')

cats = {}
for name, icon in [
    ('Vins', 'fa-wine-glass'),
    ('Softs', 'fa-glass-water'),
]:
    cat, _ = Categorie.objects.get_or_create(name=name, defaults={'icon': icon})
    if not cat.icon:
        cat.icon = icon
        cat.save(update_fields=['icon'])
    cats[name] = cat

rows = [
    # VINS (noms simplifiés demandés)
    ('Vins', '🍷 Vaucluse Blanc 25', '3.50'),
    ('Vins', '🍷 Vaucluse Blanc 50', '6.00'),
    ('Vins', '🍷 Domaine Vic Chardonnay Blanc 25', '5.00'),
    ('Vins', '🍷 Domaine Vic Chardonnay Blanc 50', '8.00'),
    ('Vins', '🍷 Vaucluse Rosé 25', '3.50'),
    ('Vins', '🍷 Vaucluse Rosé 50', '6.00'),
    ('Vins', '🍷 Domaine Vic Grenache Rosé 25', '5.00'),
    ('Vins', '🍷 Domaine Vic Grenache Rosé 50', '8.00'),
    ('Vins', '🍷 Vaucluse Rouge 25', '3.50'),
    ('Vins', '🍷 Vaucluse Rouge 50', '6.00'),

    # SOFTS
    ('Softs', '🥤 Eau 50cl', '1.00'),
    ('Softs', '🥤 Coca-Cola 33cl', '2.00'),
    ('Softs', '🥤 Coca-Cola Zéro 33cl', '2.00'),
    ('Softs', '🥤 Fuze Tea 33cl', '2.00'),
    ('Softs', '🥤 Orangina 33cl', '2.00'),
    ('Softs', '🥤 Red Bull 25cl', '2.50'),
    ('Softs', '🥤 Quillons / Coupes', '1.00'),
]

created = 0
updated = 0
for cat_name, art_name, prix in rows:
    art, was_created = Articles.objects.get_or_create(
        name=art_name,
        defaults={
            'prix': Decimal(prix),
            'prix_achat': Decimal('0.00'),
            'categorie': cats[cat_name],
            'methode': vente,
            'methode_choices': Articles.VENTE,
            'archive': False,
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
        if changed:
            art.save()
            updated += 1

    pdv.articles.add(art)

print('PDV', pdv.id, pdv.name)
print('CREATED', created, 'UPDATED', updated, 'TOTAL_LINKED', pdv.articles.filter(archive=False).count())
for a in pdv.articles.filter(archive=False).select_related('categorie').order_by('categorie__name', 'name'):
    print(f"- {a.categorie.name} | {a.name} | {a.prix}")
