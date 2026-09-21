from decimal import Decimal
import json
from APIcashless.models import PointDeVente, Categorie, Articles, Methode

pdv, _ = PointDeVente.objects.get_or_create(
    name="PIAN'S PRINCIPAL",
    defaults={
        'comportement': 'A',
        'accepte_especes': True,
        'accepte_carte_bancaire': True,
        'accepte_commandes': False,
    }
)
vente, _ = Methode.objects.get_or_create(name='VenteArticle')

cats = {}
for name, icon in [
    ('Bières', 'fa-beer'),
    ('Cocktails', 'fa-cocktail'),
    ('Softs', 'fa-glass-water'),
    ('Vins', 'fa-wine-glass'),
]:
    cat, _ = Categorie.objects.get_or_create(name=name, defaults={'icon': icon})
    if not cat.icon:
        cat.icon = icon
        cat.save(update_fields=['icon'])
    cats[name] = cat

rows = [
    ('Bières', 'La Mordue Hard Cider (6°) 25cl', '4.00', '3.00'),
    ('Bières', 'La Mordue Hard Cider (6°) 50cl', '6.50', '5.00'),
    ('Bières', 'Kohlneim (4.2°) 25cl', '3.50', '2.50'),
    ('Bières', 'Kohlneim (4.2°) 50cl', '6.00', '4.50'),
    ('Bières', 'Chouffe (8°) 25cl', '4.50', '4.00'),
    ('Bières', 'Chouffe (8°) 50cl', '7.00', '5.50'),
    ('Bières', 'Cherry Chouffe (8°) 25cl', '4.50', '4.00'),
    ('Bières', 'Cherry Chouffe (8°) 50cl', '7.00', '5.50'),
    ('Cocktails', 'BlackBull 33cl', '6.00', '5.00'),
    ('Cocktails', 'Havana Mojito 25cl', '6.00', '5.00'),
    ('Cocktails', 'Moscow Mule 25cl', '6.00', '5.00'),
    ('Softs', 'Eau 50cl', '1.00', None),
    ('Softs', 'Coca-Cola 33cl', '2.00', None),
    ('Softs', 'Coca-Cola Zéro 33cl', '2.00', None),
    ('Softs', 'Fuze Tea 33cl', '2.00', None),
    ('Softs', 'Orangina 33cl', '2.00', None),
    ('Softs', 'Red Bull 25cl', '2.50', None),
    ('Softs', 'Quillons', '1.00', None),
]

bar_key = "pian's principal"
hh_map = {'bars': {bar_key: {}}}

for cat_name, art_name, prix, prix_hh in rows:
    art, _ = Articles.objects.get_or_create(
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

    pdv.articles.add(art)

    if prix_hh is not None:
        hh_value = f"{Decimal(prix_hh):.2f}"
        hh_map['bars'][bar_key][str(art.id)] = hh_value
        hh_map['bars'][bar_key][art.name.lower()] = hh_value

with open('/DjangoFiles/www/happy_hour_prices.json', 'w', encoding='utf-8') as f:
    json.dump(hh_map, f, ensure_ascii=False, indent=2)

print('PDV', pdv.id, pdv.name, 'articles', pdv.articles.count())
print('CATS', list(Categorie.objects.filter(name__in=['Bières', 'Cocktails', 'Softs', 'Vins']).values_list('name', flat=True)))
print('HH keys', len(hh_map['bars'][bar_key]))
