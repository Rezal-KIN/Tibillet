import logging
import json
import base64
import os
import re

from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import Sum
from django.db.models import Q
from django.db.models.functions import TruncMinute
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone

from fedow_core.models import Asset, Place, Wallet, Card, Federation, Transaction, Token
from fedow_core.models import Configuration

logger = logging.getLogger(__name__)
PARIS_TZ = ZoneInfo("Europe/Paris")
TRACKED_BAR_LABELS = ["PIAN'S (18 produits)", "oenol'ss", "shots"]
SUIVI_SESSION_MARKER_PATH = "/home/fedow/Fedow/www/suivi_session_start.txt"
MONETARY_CATEGORIES = [Asset.STRIPE_FED_FIAT, Asset.TOKEN_LOCAL_FIAT, Asset.TOKEN_LOCAL_NOT_FIAT]
SPEND_ACTIONS = [Transaction.SALE, Transaction.QRCODE_SALE]


def badgeuse_view(request, pk):
    asset = get_object_or_404(Asset, pk=pk)

    ligne_badgeuse = asset.transactions.filter(
        action=Transaction.BADGE).order_by('card', 'datetime')

    dict_carte_passage = {}
    for ligne in ligne_badgeuse:
        ligne: Transaction
        if ligne.card not in dict_carte_passage:
            dict_carte_passage[ligne.card] = []
        dict_carte_passage[ligne.card].append(ligne)

    passages = []
    for carte, transactions in dict_carte_passage.items():
        horaires = [transaction.datetime for transaction in transactions]
        horaires_sorted = sorted(horaires)
        if len(horaires_sorted) % 2 != 0:
            horaires_sorted.append(None)

        couples_de_passage = list(zip(horaires_sorted[::2], horaires_sorted[1::2]))
        for horaires in couples_de_passage:
            index = couples_de_passage.index(horaires) * 2
            passages.append({carte: {
                'horaires': horaires,
                'transaction': transactions[index],
            }
            })

    context = {
        'passages': passages,
    }

    return render(request, 'asset/badgeuse.html', context=context)


def asset_view(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    if asset.category == Asset.BADGE:
        return badgeuse_view(request, pk)

    context = {
        'asset': asset,
        'transactions': asset.transactions.all().order_by('-datetime')[:50],
    }
    if asset.category == Asset.SUBSCRIPTION:
        return render(request, 'asset/asset_transactions_membership.html', context=context)
    return render(request, 'asset/asset_transactions.html', context=context)


def place_view(request, pk):
    place = get_object_or_404(Place, pk=pk)
    accepted_assets = place.accepted_assets()
    place_federated_with = place.federated_with()

    context = {
        'assets': accepted_assets,
        'federations': place.federations.all(),
        'places': place_federated_with,
        'wallets': Wallet.objects.all(),
        'cards': Card.objects.all(),
    }
    return render(request, 'place/place.html', context=context)


def index(request):
    places = Place.objects.all().order_by("name")
    assets = Asset.objects.filter(archive=False)
    monetary_assets = assets.filter(category__in=MONETARY_CATEGORIES).order_by("name")

    context = {
        'federations': Federation.objects.all(),
        'assets': assets,
        'places': places,
        'wallets': Wallet.objects.all(),
        'cards': Card.objects.all(),
        'monetary_assets': monetary_assets,
    }
    return render(request, 'index/index.html', context=context)


def _to_eur(value):
    if value is None:
        return Decimal("0.00")
    return (Decimal(value) / Decimal("100")).quantize(Decimal("0.01"))


def _extract_bar_name_from_metadata(metadata_raw):
    try:
        obj = metadata_raw
        if isinstance(metadata_raw, str):
            obj = json.loads(metadata_raw)
        if not isinstance(obj, dict):
            return None

        signed_data = obj.get("data")
        if not isinstance(signed_data, str) or not signed_data:
            return None

        payload = signed_data.split(":", 1)[0]
        payload += "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8", errors="ignore")
        match = re.search(r"<PointDeVente: ([^>]+)>", decoded)
        return match.group(1).strip() if match else None
    except Exception:
        return None


def _normalize_bar_name(name):
    if not name:
        return ""
    n = str(name).strip().lower()
    n = n.replace("'", "'")
    n = n.replace("`", "'")
    n = n.replace(" ", "")
    return n


def _bar_label_from_raw_name(raw_name):
    if not raw_name:
        return None
    raw = str(raw_name).strip()
    key = _normalize_bar_name(raw)
    if key in {"pian's", "pians"}:
        if raw == "PIAN'S":
            return "PIAN'S (18 produits)"
        return None
    if key == "oenol'ss":
        return "oenol'ss"
    if key == "shots":
        return "shots"
    return raw


def _match_selected_bar(raw_bar_name, selected_label):
    if not selected_label:
        return True
    if selected_label == "PIAN'S (18 produits)":
        return str(raw_bar_name).strip() == "PIAN'S"
    return _normalize_bar_name(raw_bar_name) == _normalize_bar_name(selected_label)


def _parse_time_flexible(value, default):
    raw = (value or "").strip().lower()
    if not raw:
        return default, default.strftime("%H:%M")
    raw = raw.replace("h", ":").replace(".", ":")
    parts = raw.split(":")
    try:
        if len(parts) == 1:
            h = int(parts[0])
            m = 0
        else:
            h = int(parts[0])
            m = int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError
        t = time(h, m)
        return t, f"{h:02d}:{m:02d}"
    except Exception:
        return default, default.strftime("%H:%M")


def _read_suivi_session_start(now_dt):
    try:
        if not os.path.exists(SUIVI_SESSION_MARKER_PATH):
            return None
        raw = open(SUIVI_SESSION_MARKER_PATH, "r", encoding="utf-8").read().strip()
        if not raw:
            return None
        marker = datetime.fromisoformat(raw)
        if marker.tzinfo is None:
            marker = timezone.make_aware(marker, PARIS_TZ)
        marker = timezone.localtime(marker, PARIS_TZ)
        if marker > now_dt:
            return None
        return marker
    except Exception:
        return None


def _money_snapshot_and_series(start_dt, end_dt, place=None, bar_name=None):
    tx_qs = Transaction.objects.filter(
        datetime__gte=start_dt,
        datetime__lte=end_dt,
        asset__category__in=MONETARY_CATEGORIES,
    )
    if place:
        tx_qs = tx_qs.filter(
            Q(action=Transaction.REFILL, sender=place.wallet)
            | Q(action__in=SPEND_ACTIONS, receiver=place.wallet)
        )
    if bar_name:
        matched_ids = []
        for tx_id, tx_meta in tx_qs.filter(action__in=SPEND_ACTIONS).values_list("uuid", "metadata"):
            raw_bar = _extract_bar_name_from_metadata(tx_meta)
            if raw_bar and _match_selected_bar(raw_bar, bar_name):
                matched_ids.append(tx_id)
        tx_qs = tx_qs.filter(action=Transaction.REFILL) | tx_qs.filter(uuid__in=matched_ids)

    total_recharged = tx_qs.filter(action=Transaction.REFILL).aggregate(total=Sum("amount"))["total"] or 0
    total_spent = tx_qs.filter(action__in=SPEND_ACTIONS).aggregate(total=Sum("amount"))["total"] or 0

    recharge_rows = (
        tx_qs.filter(action=Transaction.REFILL)
        .annotate(ts=TruncMinute("datetime"))
        .values("ts")
        .annotate(total=Sum("amount"))
        .order_by("ts")
    )
    spent_rows = (
        tx_qs.filter(action__in=SPEND_ACTIONS)
        .annotate(ts=TruncMinute("datetime"))
        .values("ts")
        .annotate(total=Sum("amount"))
        .order_by("ts")
    )

    recharge_map = {row["ts"]: row["total"] or 0 for row in recharge_rows}
    spent_map = {row["ts"]: row["total"] or 0 for row in spent_rows}

    start_min = start_dt.replace(second=0, microsecond=0)
    end_min = end_dt.replace(second=0, microsecond=0)
    all_points = sorted(set([start_min, end_min] + list(recharge_map.keys()) + list(spent_map.keys())))

    labels = []
    total_curve = []
    spent_curve = []
    wallet_curve = []
    c_recharged = 0
    c_spent = 0

    for point in all_points:
        c_recharged += recharge_map.get(point, 0)
        c_spent += spent_map.get(point, 0)
        c_wallet = max(c_recharged - c_spent, 0)

        labels.append(timezone.localtime(point, PARIS_TZ).strftime("%H:%M"))
        total_curve.append(float(_to_eur(c_recharged)))
        spent_curve.append(float(_to_eur(c_spent)))
        wallet_curve.append(float(_to_eur(c_wallet)))

    if place:
        wallets_total = max(total_recharged - total_spent, 0)
    else:
        wallets_total = (
            Token.objects.filter(
                wallet__place__isnull=True,
                asset__category__in=MONETARY_CATEGORIES,
            ).aggregate(total=Sum("value"))["total"]
            or 0
        )

    return {
        "period": {
            "start": timezone.localtime(start_dt, PARIS_TZ).isoformat(),
            "end": timezone.localtime(end_dt, PARIS_TZ).isoformat(),
        },
        "filters": {
            "place_uuid": str(place.uuid) if place else "",
            "place_name": place.name if place else "Tous les bars",
            "bar_name": bar_name or "",
        },
        "totals": {
            "recharged_eur": float(_to_eur(total_recharged)),
            "spent_eur": float(_to_eur(total_spent)),
            "wallet_remaining_eur": float(_to_eur(max(total_recharged - total_spent, 0))),
            "wallet_live_total_eur": float(_to_eur(wallets_total)),
        },
        "series": {
            "labels": labels,
            "recharged": total_curve,
            "spent": spent_curve,
            "wallet_remaining": wallet_curve,
        },
    }


def _parse_suivi_filters(request):
    now = timezone.localtime(timezone.now(), PARIS_TZ)
    has_start_param = request.GET.get("start") is not None

    place_uuid = (request.GET.get("place") or "").strip()
    place = Place.objects.filter(uuid=place_uuid).first() if place_uuid else None

    start_t, start_raw = _parse_time_flexible(request.GET.get("start"), time(0, 0))
    end_t, end_raw = _parse_time_flexible(request.GET.get("end"), now.time().replace(second=0, microsecond=0))
    bar_name = (request.GET.get("bar") or "").strip()

    start_dt = timezone.make_aware(datetime.combine(now.date(), start_t), PARIS_TZ)
    if start_dt > now:
        start_dt -= timedelta(days=1)
    session_start = _read_suivi_session_start(now)
    if (not has_start_param) and session_start and session_start > start_dt:
        start_dt = session_start
        start_raw = session_start.strftime("%H:%M")

    end_dt = timezone.make_aware(datetime.combine(start_dt.date(), end_t), PARIS_TZ)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    if end_dt > now:
        end_dt = now

    return {
        "place": place,
        "place_uuid": place_uuid,
        "start_raw": start_raw,
        "end_raw": end_raw,
        "bar_name": bar_name,
        "start_dt": start_dt,
        "end_dt": end_dt,
        "now": now,
    }


def suivi(request):
    f = _parse_suivi_filters(request)
    data = _money_snapshot_and_series(
        start_dt=f["start_dt"],
        end_dt=f["end_dt"],
        place=f["place"],
        bar_name=f["bar_name"],
    )
    places = Place.objects.all().order_by("name")
    bar_names = list(TRACKED_BAR_LABELS)
    for tx_meta in Transaction.objects.filter(action__in=SPEND_ACTIONS).values_list("metadata", flat=True):
        raw_bar = _extract_bar_name_from_metadata(tx_meta)
        label = _bar_label_from_raw_name(raw_bar)
        if label and label not in bar_names:
            bar_names.append(label)
    bar_names = sorted(bar_names, key=lambda x: x.lower())
    context = {
        "initial_data_json": json.dumps(data),
        "refresh_seconds": 30,
        "places": places,
        "bar_names": bar_names,
        "selected_place_uuid": f["place_uuid"],
        "selected_bar_name": f["bar_name"],
        "selected_start": f["start_raw"],
        "selected_end": f["end_raw"],
    }
    return render(request, "index/suivi.html", context=context)


def suivi_data(request):
    f = _parse_suivi_filters(request)
    data = _money_snapshot_and_series(
        start_dt=f["start_dt"],
        end_dt=f["end_dt"],
        place=f["place"],
        bar_name=f["bar_name"],
    )
    return JsonResponse(data)
