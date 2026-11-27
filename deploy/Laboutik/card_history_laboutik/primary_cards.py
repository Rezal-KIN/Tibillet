"""Onglet admin « Cartes primaires (NFC) » : enchaîne les étapes natives de LaBoutik.

FR : 1) la carte est retrouvée (ou enregistrée depuis Fedow, comme « Vérifier carte ») ;
2) son membre est créé ou renommé ; 3) la carte primaire native est créée ou mise à
jour (points de vente, mode gérant). Les signaux natifs préviennent Fedow. Rien n'est
supprimé : retirer une carte primaire supprime seulement l'objet CarteMaitresse, comme
dans l'admin. Réservé aux personnes connectées à l'admin LaBoutik (admin_view).
EN: Admin tab chaining LaBoutik's native primary-card steps; staff only.
"""
import json
import logging
import re

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)
HEX8 = re.compile(r'^[0-9A-F]{8}$')


def candidates(raw):
    """Identifiants possibles selon le lecteur (Web NFC « 04:a2:… », clavier hexa ou décimal)."""
    value = re.sub(r'[\s:\-]', '', (raw or '')).upper()
    result = []
    if re.fullmatch(r'[0-9A-F]{8}', value):
        result += [value, ''.join(reversed([value[i:i + 2] for i in range(0, 8, 2)]))]
    if re.fullmatch(r'[0-9]{1,10}', value) and int(value) < 2 ** 32:
        as_hex = '%08X' % int(value)
        result += [as_hex, ''.join(reversed([as_hex[i:i + 2] for i in range(0, 8, 2)]))]
    unique = []
    for tag in result:
        if tag not in unique:
            unique.append(tag)
    return unique


def fedow_tag_from_number(number):
    """Numéro imprimé → identifiant NFC, via la route Fedow signée du lieu (lecture seule)."""
    from APIcashless.models import Configuration
    from fedow_connect.fedow_api import _get
    response = _get(Configuration.get_solo(), path=['card_history', 'number', number])
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()['card']['tag_id']


def find_card(raw, mode='scan'):
    """
    Carte LaBoutik existante, sinon enregistrée depuis Fedow (cartes du stock uniquement).
    mode « scan » : identifiant NFC lu par le téléphone.
    mode « numero » : numéro imprimé saisi sur ordinateur, puis identifiant tapé par un
    lecteur USB « clavier » en secours.
    """
    from APIcashless.models import CarteCashless
    from fedow_connect.fedow_api import FedowAPI
    value = re.sub(r'[\s:\-]', '', (raw or '')).upper()
    tags = []
    if mode == 'numero' and re.fullmatch(r'[0-9A-Z]{8}', value):
        card = CarteCashless.objects.filter(number=value).first()
        if card:
            return card
        tag = fedow_tag_from_number(value)
        if tag:
            tags.append(tag)
    tags += [tag for tag in candidates(raw) if tag not in tags]
    card = CarteCashless.objects.filter(tag_id__in=tags).first()
    if card:
        return card
    for tag in tags:
        try:
            FedowAPI().NFCcard.retrieve(tag)  # natif : crée la carte locale depuis Fedow
        except FileNotFoundError:
            continue
        card = CarteCashless.objects.filter(tag_id=tag).first()
        if card:
            return card
    return None


def describe(card):
    from APIcashless.models import CarteMaitresse
    primary = CarteMaitresse.objects.filter(carte=card).first()
    membre = card.membre
    return {
        'tag_id': card.tag_id,
        'number': card.number,
        'nom': membre.name if membre else '',
        'prenom': (membre.prenom or '') if membre else '',
        # Carte liée au compte d'un client (e-mail) : on ne renomme pas son membre.
        'customer_email': membre.email if membre and membre.email else None,
        'primary': None if primary is None else {
            'pos': [str(pk) for pk in primary.points_de_vente.values_list('pk', flat=True)],
            'gerant': primary.edit_mode,
        },
    }


def page(request):
    from APIcashless.models import PointDeVente
    from administration.adminstaff import staff_admin_site
    # Comme les vues natives de l'admin : le menu Jet résout ses liens pour ce site.
    request.current_app = staff_admin_site.name
    context = dict(staff_admin_site.each_context(request))
    context.update({
        'title': 'Cartes primaires (NFC)',
        'points_de_vente': PointDeVente.objects.filter(hidden=False).order_by('poid_liste', 'name'),
    })
    return render(request, 'card_history_laboutik/primary_cards.html', context)


def body(request):
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except ValueError:
        return {}


def lookup(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST requis'}, status=405)
    data = body(request)
    try:
        card = find_card(data.get('value'), 'numero' if data.get('mode') == 'numero' else 'scan')
    except Exception as error:
        logger.error(f"primary_cards lookup : {type(error).__name__}")
        return JsonResponse({'error': "Fedow injoignable, réessayez."}, status=502)
    if card is None:
        return JsonResponse({'error': "Carte inconnue : elle ne fait pas partie du stock du gala."}, status=404)
    return JsonResponse(describe(card))


def save(request):
    from APIcashless.models import CarteCashless, CarteMaitresse, Membre, PointDeVente
    if request.method != 'POST':
        return JsonResponse({'error': 'POST requis'}, status=405)
    data = body(request)
    tag = (data.get('tag_id') or '').upper()
    nom = (data.get('nom') or '').strip()
    prenom = (data.get('prenom') or '').strip()
    pos_ids = [str(pk) for pk in data.get('pos') or []]
    if not HEX8.match(tag):
        return JsonResponse({'error': "Scannez d'abord une carte."}, status=400)
    points = list(PointDeVente.objects.filter(pk__in=pos_ids))
    if not points or len(points) != len(set(pos_ids)):
        return JsonResponse({'error': "Choisissez au moins un point de vente."}, status=400)
    try:
        with transaction.atomic():
            card = CarteCashless.objects.select_for_update().get(tag_id=tag)
            membre = card.membre
            if membre is None:
                if not nom:
                    return JsonResponse({'error': "Indiquez le nom de la personne."}, status=400)
                membre = Membre.objects.create(name=nom[:50], prenom=prenom[:50] or None)
                card.membre = membre
                card.save()
            elif not membre.email and nom:
                membre.name, membre.prenom = nom[:50], (prenom[:50] or None)
                membre.save()
            primary, _ = CarteMaitresse.objects.get_or_create(carte=card)
            primary.edit_mode = bool(data.get('gerant'))
            primary.save()  # signal natif : Fedow set_primary (synchrone)
            primary.points_de_vente.set(points)
    except CarteCashless.DoesNotExist:
        return JsonResponse({'error': "Carte introuvable, scannez-la à nouveau."}, status=404)
    except Exception as error:
        logger.error(f"primary_cards save {tag} : {type(error).__name__}: {error}")
        return JsonResponse({'error': "Enregistrement impossible (Fedow ?). Rien n'a été modifié."}, status=502)
    return JsonResponse({'ok': True, 'card': describe(card)})


def remove(request):
    from APIcashless.models import CarteMaitresse
    if request.method != 'POST':
        return JsonResponse({'error': 'POST requis'}, status=405)
    tag = (body(request).get('tag_id') or '').upper()
    try:
        with transaction.atomic():
            primary = CarteMaitresse.objects.filter(carte__tag_id=tag).first()
            if primary is None:
                return JsonResponse({'error': "Cette carte n'est pas une carte primaire."}, status=404)
            card = primary.carte
            primary.delete()  # signal natif : Fedow set_primary(delete=True)
    except Exception as error:
        logger.error(f"primary_cards remove {tag} : {type(error).__name__}")
        return JsonResponse({'error': "Retrait impossible (Fedow ?). Rien n'a été modifié."}, status=502)
    return JsonResponse({'ok': True, 'card': describe(card)})


def urls():
    """Routes de l'onglet, protégées par la connexion à l'admin LaBoutik."""
    from django.urls import path
    from administration.adminstaff import staff_admin_site
    guard = staff_admin_site.admin_view
    return [
        # Sous l'admin, comme les autres modules : /adminstaff/cartes-primaires/
        path('adminstaff/cartes-primaires/', guard(page), name='gala-primary-cards'),
        path('adminstaff/cartes-primaires/carte/', guard(lookup), name='gala-primary-cards-lookup'),
        path('adminstaff/cartes-primaires/enregistrer/', guard(save), name='gala-primary-cards-save'),
        path('adminstaff/cartes-primaires/retirer/', guard(remove), name='gala-primary-cards-remove'),
    ]
