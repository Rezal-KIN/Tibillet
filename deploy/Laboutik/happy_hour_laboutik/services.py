"""Happy hour : le serveur reste maître du prix.

FR :
- Les caisses reçoivent les prix en vigueur au chargement, et le délai avant le
  prochain changement : elles se rechargent seules à l'heure dite (sans dépendre
  de l'horloge du téléphone), dès que le panier est vide.
- À la validation, le serveur recalcule le total. Autour d'un changement d'heure
  (marge GRACE), il accepte l'ancien ou le nouveau prix et débite exactement celui
  affiché au client. En dehors de la marge, un total incohérent reste refusé.
EN: Terminals get current prices plus a countdown to the next change; the server
recomputes totals and, only near a boundary, accepts the displayed old/new price.
"""
from datetime import datetime, timedelta
from decimal import Decimal

GRACE = timedelta(minutes=5)


def _tz():
    import pytz
    from django.conf import settings
    from APIcashless.models import Configuration
    name = Configuration.get_solo().fuseau_horaire or settings.TIME_ZONE or 'Europe/Paris'
    return pytz.timezone(name)


def _occurrences(local_now, at_time, tz):
    """Occurrences d'une heure murale hier, aujourd'hui et demain (fuseau local)."""
    result = []
    for days in (-1, 0, 1):
        day = (local_now + timedelta(days=days)).date()
        result.append(tz.localize(datetime.combine(day, at_time)))
    return result


def state(now=None):
    """État du happy hour : actif ?, prochain changement, proximité d'une bascule."""
    from happy_hour_laboutik.models import HappyHour
    config = HappyHour.get_solo()
    if not config.actif or config.debut == config.fin:
        return {'active': False, 'seconds_until_change': None, 'near_boundary': False}
    if now is None:
        from django.utils import timezone
        now = timezone.now()
    tz = _tz()
    local_now = now.astimezone(tz)
    starts = _occurrences(local_now, config.debut, tz)
    ends = _occurrences(local_now, config.fin, tz)
    # Actif si la dernière bascule passée est un début.
    last_start = max(s for s in starts if s <= local_now)
    last_end = max(e for e in ends if e <= local_now)
    active = last_start > last_end
    upcoming = min(b for b in starts + ends if b > local_now)
    last_boundary = max(last_start, last_end)
    return {
        'active': active,
        'seconds_until_change': max(1, int((upcoming - local_now).total_seconds()) + 1),
        'near_boundary': (local_now - last_boundary) < GRACE or (upcoming - local_now) < GRACE,
    }


def happy_prices(article_ids):
    from happy_hour_laboutik.models import HappyHourPrice
    # FR : Uniquement les articles de vente (jamais recharges, consignes, etc.).
    # EN: Sale articles only (never refills, deposits, etc.).
    return {str(pk): prix for pk, prix in HappyHourPrice.objects.filter(
        article_id__in=list(article_ids), article__methode_choices='VT',
    ).values_list('article_id', 'prix')}


def apply_to_payload(points_de_vente, now=None):
    """Remplace les prix des articles en vente par le prix happy hour si actif."""
    current = state(now)
    if current['active']:
        ids = {article['id'] for pdv in points_de_vente for article in pdv.get('articles', [])}
        prices = happy_prices(ids)
        for pdv in points_de_vente:
            for article in pdv.get('articles', []):
                hh = prices.get(str(article['id']))
                if hh is not None:
                    article['prix_normal'] = article['prix']
                    article['prix'] = f"{hh:.2f}"
                    article['happy_hour'] = True
    info = {'active': current['active'], 'seconds_until_change': current['seconds_until_change']}
    # FR : Recopié dans chaque point de vente : le front natif conserve `glob.data`
    # tel quel, ce qui permet au script happy hour de lire le délai sans autre requête.
    # EN: Copied into each POS because the native front keeps `glob.data` as is.
    for pdv in points_de_vente:
        pdv['happy_hour'] = info
    return info


def resolve_prices(lines, total_sent, now=None):
    """
    Fixe en mémoire le prix de chaque ligne (normal ou happy hour) pour cette vente.
    Retourne le total recalculé. Lève ValueError si le total envoyé ne correspond à
    aucun barème autorisé à cet instant.
    """
    def dround(value):
        return Decimal(value).quantize(Decimal('1.00'))

    articles = [line['pk'] for line in lines]
    current = state(now)
    prices = happy_prices(a.pk for a in articles) if (current['active'] or current['near_boundary']) else {}

    def total(use_happy):
        result = Decimal(0)
        for line in lines:
            result += dround(unit_price(line['pk'], use_happy) * line['qty'])
        return result

    def unit_price(article, use_happy):
        hh = prices.get(str(article.pk)) if use_happy else None
        if hh is not None:
            return hh
        return article.prix

    modes = [current['active']]
    if current['near_boundary']:
        modes.append(not current['active'])
    chosen = None
    if total_sent is None:
        chosen = modes[0]
    else:
        for mode in modes:
            # Valeur absolue comme le natif, pour les retours de consigne négatifs.
            if abs(total(mode)) == abs(total_sent):
                chosen = mode
                break
    if chosen is None:
        raise ValueError(f"total {total_sent} != {[str(total(m)) for m in modes]}")
    for line in lines:
        # FR : Surcharge en mémoire pour cette requête uniquement (jamais enregistrée).
        # EN: In-memory override for this request only, never saved.
        line['pk'].prix = unit_price(line['pk'], chosen)
    return total(chosen)
