"""Import idempotent du catalogue Gala dans LaBoutik (à lancer dans `manage.py shell`).

FR :
- Entrée : JSON (variable d'environnement GALA_CATALOGUE_JSON) produit depuis l'Excel des
  pians : points de vente, articles, prix et prix happy hour.
- Crée ou met à jour catégories, articles et points de vente par leur nom ; la liste
  d'articles de chaque point de vente devient exactement celle de l'Excel.
- Ne supprime rien. Les points de vente/articles absents de l'Excel sont laissés tels
  quels, sauf ceux listés dans GALA_CATALOGUE_HIDE (points de vente masqués) ou
  GALA_CATALOGUE_ARCHIVE (articles archivés), jamais supprimés.
- Les prix happy hour et la plage horaire nécessitent le module happy_hour_laboutik.
- DRY_RUN=1 : tout est calculé dans une transaction annulée à la fin.
EN: Idempotent Gala catalogue import; never deletes; DRY_RUN=1 rolls everything back.
"""
import json
import os
from datetime import time
from decimal import Decimal

from django.db import transaction

from APIcashless.models import Articles, Categorie, PointDeVente

catalogue = json.loads(os.environ['GALA_CATALOGUE_JSON'])
hide = [name for name in os.environ.get('GALA_CATALOGUE_HIDE', '').split('|') if name]
archive = [name for name in os.environ.get('GALA_CATALOGUE_ARCHIVE', '').split('|') if name]
dry_run = os.environ.get('DRY_RUN') == '1'

ICONS = {'Bières ATS': 'fa-beer', 'Cocktails ATS': 'fa-cocktail', 'Shots ATS': 'fa-glass-whiskey',
         'KDB': 'fa-glass-cheers', 'ZZ': 'fa-beer', 'Centrale': 'fa-glass-martini', 'Zstrass': 'fa-beer'}
NATIVE = {'Consigne', 'Retour Consigne'}


class DryRun(Exception):
    pass


report = {'created': [], 'updated': [], 'hidden': [], 'points_de_vente': {}}
try:
    with transaction.atomic():
        categories = {}
        for article in catalogue['articles']:
            name = article['categorie']
            if name not in categories:
                categories[name], created = Categorie.objects.get_or_create(name=name)
                if created:
                    report['created'].append('categorie:' + name)

        articles = {}
        for row in catalogue['articles']:
            prix = Decimal(row['prix']).quantize(Decimal('0.01'))
            matches = list(Articles.objects.filter(name=row['name'], methode_choices=Articles.VENTE))
            if len(matches) > 1:
                raise ValueError('article en double : ' + row['name'])
            if matches:
                article = matches[0]
                changed = []
                if article.prix != prix:
                    article.prix = prix
                    changed.append('prix')
                if article.categorie_id != categories[row['categorie']].pk:
                    article.categorie = categories[row['categorie']]
                    changed.append('categorie')
                if article.archive:
                    article.archive = False
                    changed.append('archive')
                if changed:
                    article.save()
                    report['updated'].append(row['name'] + ':' + ','.join(changed))
            else:
                # .save() via create : les signaux natifs fixent méthode et ordre d'affichage.
                article = Articles.objects.create(name=row['name'], prix=prix, categorie=categories[row['categorie']],
                                                  methode_choices=Articles.VENTE)
                report['created'].append('article:' + row['name'])
            articles[row['name']] = article

        for name in NATIVE:
            articles[name] = Articles.objects.get(name=name)

        for name, content in catalogue['points_de_vente'].items():
            pdv, created = PointDeVente.objects.get_or_create(name=name, defaults={
                'comportement': PointDeVente.VENTE, 'service_direct': True, 'accepte_commandes': False,
                # Gala : espèces et CB uniquement au point de vente Cashless (recharges).
                'accepte_especes': False, 'accepte_carte_bancaire': False, 'afficher_les_prix': True,
                'icon': ICONS.get(name, 'fa-beer'),
            })
            if created:
                report['created'].append('point_de_vente:' + name)
            if pdv.hidden:
                pdv.hidden = False
                pdv.save()
            pdv.articles.set([articles[article] for article in content])
            report['points_de_vente'][name] = sorted(pdv.articles.values_list('name', flat=True))

        for name in hide:
            updated = PointDeVente.objects.filter(name=name, hidden=False).update(hidden=True)
            if updated:
                report['hidden'].append(name)

        # Articles retirés des caisses : archivés (le signal natif les retire des
        # points de vente), jamais supprimés : l'historique des ventes est conservé.
        for name in archive:
            for article in Articles.objects.filter(name=name, archive=False):
                article.archive = True
                article.save()
                report['hidden'].append('article:' + name)

        # Article « Carte perdue » (1 €) dans le point de vente des recharges.
        lost = catalogue.get('carte_perdue')
        if lost:
            category, _ = Categorie.objects.get_or_create(name=lost['categorie'])
            article, created = Articles.objects.get_or_create(
                name=lost['name'], methode_choices=Articles.VENTE,
                defaults={'prix': Decimal(lost['prix']), 'categorie': category})
            if not created and article.prix != Decimal(lost['prix']):
                article.prix = Decimal(lost['prix'])
                article.save()
            if created:
                report['created'].append('article:' + lost['name'])
            for pdv in PointDeVente.objects.filter(name__in=lost['points_de_vente']):
                pdv.articles.add(article)
                report['points_de_vente'][pdv.name] = sorted(pdv.articles.values_list('name', flat=True))

        # Couleurs et icônes des boutons de caisse (portées par la catégorie).
        from APIcashless.models import Couleur
        for name, style in (catalogue.get('categories_style') or {}).items():
            category = Categorie.objects.filter(name=name).first()
            if category is None:
                continue
            category.icon = style['icon']
            category.couleur_backgr = Couleur.objects.get(name=style['fond'])
            category.couleur_texte = Couleur.objects.get(name=style['texte'])
            category.save()
            report['updated'].append('style:' + name)

        # Happy hour : prix par article (champ vide = pas de happy hour) + plage horaire.
        from happy_hour_laboutik.models import HappyHour, HappyHourPrice
        happy = {}
        for row in catalogue['articles']:
            article = articles[row['name']]
            if row.get('happy_hour'):
                prix = Decimal(row['happy_hour']).quantize(Decimal('0.01'))
                HappyHourPrice.objects.update_or_create(article=article, defaults={'prix': prix})
                happy[row['name']] = str(prix)
            else:
                HappyHourPrice.objects.filter(article=article).delete()
        window = catalogue.get('happy_hour_window')
        if window:
            schedule = HappyHour.get_solo()
            schedule.actif = True
            schedule.debut = time.fromisoformat(window['debut'])
            schedule.fin = time.fromisoformat(window['fin'])
            schedule.save()
        report['happy_hour'] = {'prices': happy, 'window': window}

        if dry_run:
            raise DryRun()
except DryRun:
    report['dry_run'] = True

print('GALA_CATALOGUE_REPORT=' + json.dumps(report, ensure_ascii=False, sort_keys=True))
