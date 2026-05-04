import logging
import json
import base64
import os
import re

from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import stripe
from django.contrib import messages
from django.core.signing import Signer
from django.db.models import Sum
from django.db.models import Q
from django.db.models.functions import TruncMinute
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.text import slugify
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from fedow_core.models import Asset, Place, Wallet, Card, Federation, Transaction, Token
from fedow_core.models import Configuration, CheckoutStripe
from fedow_core.models import asset_creator
from fedow_core.utils import dict_to_b64_utf8, utf8_b64_to_dict

logger = logging.getLogger(__name__)
PARIS_TZ = ZoneInfo("Europe/Paris")
TRACKED_BAR_LABELS = ["PIAN'S (18 produits)", "oenol'ss", "shots"]
SUIVI_SESSION_MARKER_PATH = "/home/fedow/Fedow/www/suivi_session_start.txt"
ACTIVE_GALA_CONTEXT_PATH = "/home/fedow/Fedow/www/active_gala_context.json"
GALA_PROVISION_REQUESTS_PATH = "/home/fedow/Fedow/www/gala_provision_requests.json"
MONETARY_CATEGORIES = [Asset.STRIPE_FED_FIAT, Asset.TOKEN_LOCAL_FIAT, Asset.TOKEN_LOCAL_NOT_FIAT]
SPEND_ACTIONS = [Transaction.SALE, Transaction.QRCODE_SALE]
LABOUTIK_ROOT = "/home/ubuntu/TiBillet"
LABOUTIK_DELETE_REQUESTS_PATH = "/home/fedow/Fedow/www/laboutik_delete_requests.json"


def _read_delete_requests():
    try:
        if not os.path.exists(LABOUTIK_DELETE_REQUESTS_PATH):
            return []
        raw = open(LABOUTIK_DELETE_REQUESTS_PATH, "r", encoding="utf-8").read().strip()
        return json.loads(raw) if raw else []
    except Exception:
        return []


def _append_delete_request(item):
    items = _read_delete_requests()
    items.append(item)
    os.makedirs(os.path.dirname(LABOUTIK_DELETE_REQUESTS_PATH), exist_ok=True)
    with open(LABOUTIK_DELETE_REQUESTS_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def _list_laboutik_instances():
    pending_deletions = {r["instance_name"] for r in _read_delete_requests()
                         if r.get("status") in ("pending", "processing")}
    instances = []
    try:
        for entry in os.scandir(LABOUTIK_ROOT):
            if not entry.is_dir():
                continue
            if not re.fullmatch(r"Laboutik_[a-z0-9\-]+", entry.name):
                continue
            slug = entry.name[len("Laboutik_"):]
            project_name = f"laboutik_{slug}"
            deletion_pending = entry.name in pending_deletions
            instances.append({
                "name": entry.name,
                "slug": slug,
                "project_name": project_name,
                "path": entry.path,
                "deletion_pending": deletion_pending,
            })
    except Exception:
        pass
    return sorted(instances, key=lambda x: x["name"])


def _default_active_context():
    places = list(Place.objects.all().order_by("name"))
    assets = list(Asset.objects.filter(archive=False, category__in=MONETARY_CATEGORIES).order_by("name"))

    selected_place = places[0] if places else None
    selected_asset = next((a for a in assets if a.category == Asset.TOKEN_LOCAL_FIAT), None)
    if not selected_asset and assets:
        selected_asset = assets[0]

    return {
        "active_place_uuid": str(selected_place.uuid) if selected_place else "",
        "active_asset_uuid": str(selected_asset.uuid) if selected_asset else "",
        "freeze_others": True,
        "updated_at": timezone.now().isoformat(),
    }


def _read_active_context():
    default_data = _default_active_context()
    try:
        if not os.path.exists(ACTIVE_GALA_CONTEXT_PATH):
            _write_active_context(default_data)
            return default_data
        with open(ACTIVE_GALA_CONTEXT_PATH, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            _write_active_context(default_data)
            return default_data
        data = json.loads(raw)
        if not isinstance(data, dict):
            _write_active_context(default_data)
            return default_data
        merged = {**default_data, **data}
        return merged
    except Exception:
        return default_data


def _write_active_context(data):
    os.makedirs(os.path.dirname(ACTIVE_GALA_CONTEXT_PATH), exist_ok=True)
    payload = {
        "active_place_uuid": str(data.get("active_place_uuid") or ""),
        "active_asset_uuid": str(data.get("active_asset_uuid") or ""),
        "freeze_others": bool(data.get("freeze_others", True)),
        "updated_at": timezone.now().isoformat(),
    }
    with open(ACTIVE_GALA_CONTEXT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload


def _active_context_with_labels():
    ctx = _read_active_context()
    place = Place.objects.filter(uuid=ctx.get("active_place_uuid")).first() if ctx.get("active_place_uuid") else None
    asset = Asset.objects.filter(uuid=ctx.get("active_asset_uuid")).first() if ctx.get("active_asset_uuid") else None
    return {
        **ctx,
        "active_place_name": place.name if place else "",
        "active_place_cashless_url": place.cashless_server_url if place else "",
        "active_asset_name": asset.name if asset else "",
        "active_asset_category": asset.category if asset else "",
    }


def _create_stripe_checkout_for_selected_asset(user, asset, place, add_metadata=None, start_return_url=None):
    config = Configuration.get_solo()
    if not config.get_stripe_api():
        return None

    stripe.api_key = config.get_stripe_api()
    email = user.email
    source_wallet = config.primary_wallet if asset.category == Asset.STRIPE_FED_FIAT else asset.wallet_origin
    if not source_wallet:
        raise ValueError(f"Source wallet missing for asset {asset.uuid}")
    id_price_stripe = asset.get_id_price_stripe()
    if not id_price_stripe:
        raise ValueError(f"Stripe price missing for asset {asset.uuid}")

    primary_token, _ = Token.objects.get_or_create(wallet=source_wallet, asset=asset)
    user_token, _ = Token.objects.get_or_create(wallet=user.wallet, asset=asset)

    metadata = {
        "primary_token": f"{primary_token.uuid}",
        "user_token": f"{user_token.uuid}",
    }
    if add_metadata:
        metadata.update(add_metadata)

    signer = Signer()
    signed_data = signer.sign(dict_to_b64_utf8(metadata))
    checkout_db = CheckoutStripe.objects.create(asset=user_token.asset, user=user, metadata=signed_data)

    if not start_return_url:
        return_url = f"https://{place.lespass_domain}/my_account/{checkout_db.uuid}/return_refill_wallet/"
    else:
        if not start_return_url.endswith("/"):
            start_return_url += "/"
        return_url = f"{start_return_url}{checkout_db.uuid}"

    data_checkout = {
        "success_url": f"{return_url}",
        "cancel_url": f"{return_url}",
        "payment_method_types": ["card"],
        "customer_email": f"{email}",
        "line_items": [{"price": f"{id_price_stripe}", "quantity": 1}],
        "mode": "payment",
        "metadata": {"signed_data": f"{signed_data}"},
        "client_reference_id": f"{user.pk}",
    }
    checkout_session = stripe.checkout.Session.create(**data_checkout)
    checkout_db.checkout_session_id_stripe = checkout_session.id
    checkout_db.save(update_fields=["checkout_session_id_stripe"])
    return checkout_session


def _validate_selected_asset_checkout_and_make_transaction(checkout_db: CheckoutStripe, wallet: Wallet):
    if checkout_db.status == CheckoutStripe.PAID:
        return checkout_db

    config = Configuration.get_solo()
    stripe.api_key = config.get_stripe_api()
    if not stripe.api_key:
        raise ValueError("Stripe API key missing")

    checkout_db.status = CheckoutStripe.PROGRESS
    checkout_db.save(update_fields=["status"])

    checkout = stripe.checkout.Session.retrieve(checkout_db.checkout_session_id_stripe)
    signed_data = (checkout.metadata or {}).get("signed_data")
    if not signed_data:
        raise ValueError("No signed_data in Stripe checkout session")

    signer = Signer()
    unsigned_data = utf8_b64_to_dict(signer.unsign(signed_data))

    primary_token = Token.objects.get(uuid=unsigned_data.get("primary_token"))
    user_token = Token.objects.get(uuid=unsigned_data.get("user_token"))

    if user_token.wallet != wallet:
        raise ValueError("Checkout wallet mismatch")
    if checkout_db.user and checkout_db.user != wallet.user:
        raise ValueError("Checkout user mismatch")
    if primary_token.asset != user_token.asset:
        raise ValueError("Checkout asset mismatch between tokens")
    if checkout_db.asset != primary_token.asset:
        raise ValueError("Checkout DB asset mismatch")

    if checkout.payment_status != "paid":
        raise ValueError(f"Stripe checkout not paid ({checkout.payment_status})")

    # Idempotence sur retour navigateur répété
    if Transaction.objects.filter(checkout_stripe=checkout_db, action=Transaction.REFILL).exists():
        checkout_db.status = CheckoutStripe.PAID
        checkout_db.save(update_fields=["status"])
        return checkout_db

    amount = int(checkout.amount_total or 0)
    if amount <= 0:
        raise ValueError("Invalid checkout amount")

    tx_metadata = signed_data

    existing_creation = Transaction.objects.filter(
        checkout_stripe=checkout_db,
        action=Transaction.CREATION,
    ).order_by("datetime").last()

    # 1) Création monétaire (si pas déjà faite)
    if not existing_creation:
        Transaction.objects.create(
            ip="127.0.0.1",
            sender=primary_token.wallet,
            receiver=primary_token.wallet,
            asset=primary_token.asset,
            amount=amount,
            action=Transaction.CREATION,
            metadata=tx_metadata,
            checkout_stripe=checkout_db,
        )

    # 2) Refill wallet user
    Transaction.objects.create(
        ip="127.0.0.1",
        sender=primary_token.wallet,
        receiver=user_token.wallet,
        asset=primary_token.asset,
        amount=amount,
        action=Transaction.REFILL,
        metadata=tx_metadata,
        checkout_stripe=checkout_db,
    )

    checkout_db.status = CheckoutStripe.PAID
    checkout_db.save(update_fields=["status"])
    return checkout_db


def _current_school_code(now_dt=None):
    now_dt = now_dt or timezone.localtime(timezone.now(), PARIS_TZ)
    # 225 => année scolaire 2025/2026 ; 226 => 2026/2027
    school_start_year = now_dt.year if now_dt.month >= 9 else now_dt.year - 1
    return f"2{school_start_year % 100:02d}"


def _normalize_gala_event(event_label):
    txt = (event_label or "").strip()
    if not txt:
        return ""
    s = slugify(txt).replace("-", "_").upper()
    return re.sub(r"[^A-Z0-9_]", "", s)


def _build_gala_identifier(event_label, school_code):
    event_norm = _normalize_gala_event(event_label)
    year_norm = re.sub(r"[^0-9]", "", (school_code or "").strip())
    if len(year_norm) != 3:
        year_norm = _current_school_code()
    if not event_norm:
        raise ValueError("event vide")
    return f"{event_norm}_{year_norm}"


def _build_gala_domain_slug(gala_id):
    return re.sub(r"[^a-z0-9]+", "-", slugify(gala_id or "")).strip("-")


def _read_provision_requests():
    try:
        if not os.path.exists(GALA_PROVISION_REQUESTS_PATH):
            return []
        with open(GALA_PROVISION_REQUESTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def _append_provision_request(item):
    items = _read_provision_requests()
    items.append(item)
    os.makedirs(os.path.dirname(GALA_PROVISION_REQUESTS_PATH), exist_ok=True)
    with open(GALA_PROVISION_REQUESTS_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def badgeuse_view(request, pk):
    asset = get_object_or_404(Asset, pk=pk)

    # Tout les actions de badgeuse sont des articles vendus avec la methode BADGEUSE
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
        for horaires in couples_de_passage :
            # On veut la transaction qui correspond au premier horaire du couple de passage
            index = couples_de_passage.index(horaires) * 2 # il y a deux fois plus de transaction que de couple horaire
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
        # seulement les 50 dernières transactions :
        'transactions': asset.transactions.all().order_by('-datetime')[:50],
    }
    if asset.category == Asset.SUBSCRIPTION:
        return render(request, 'asset/asset_transactions_membership.html', context=context)
    return render(request, 'asset/asset_transactions.html', context=context)


# Create your views here.
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


# @cache_page(60 * 15)
def index(request):
    """
    Livre un template HTML
    """
    active_context = _active_context_with_labels()
    active_place_uuid = active_context.get("active_place_uuid") or ""
    active_asset_uuid = active_context.get("active_asset_uuid") or ""
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
        'active_context': active_context,
        'active_place_uuid': active_place_uuid,
        'active_asset_uuid': active_asset_uuid,
        'suggested_school_code': _current_school_code(),
        'provision_requests': list(reversed(_read_provision_requests()))[:10],
        'laboutik_instances': _list_laboutik_instances(),
    }
    logger.info(f"Index page rendered")
    return render(request, 'index/index.html', context=context)


def active_context_set(request):
    if request.method != "POST":
        return redirect("/dashboard/")

    place_uuid = (request.POST.get("active_place_uuid") or "").strip()
    asset_uuid = (request.POST.get("active_asset_uuid") or "").strip()
    freeze_others = request.POST.get("freeze_others") == "on"

    place = Place.objects.filter(uuid=place_uuid).first() if place_uuid else None
    asset = Asset.objects.filter(uuid=asset_uuid, archive=False, category__in=MONETARY_CATEGORIES).first() if asset_uuid else None

    if not place or not asset:
        messages.error(request, "Lieu actif ou monnaie active invalide.")
        return redirect("/dashboard/")

    _write_active_context({
        "active_place_uuid": str(place.uuid),
        "active_asset_uuid": str(asset.uuid),
        "freeze_others": freeze_others,
    })
    messages.success(request, f"Lieu actif mis à jour: {place.name} | Monnaie active: {asset.name}")
    return redirect("/dashboard/")


def active_context_data(request):
    return JsonResponse(_active_context_with_labels())


@csrf_exempt
def active_context_refill_checkout(request):
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    expected_token = (os.environ.get("ACTIVE_GALA_API_TOKEN") or "").strip()
    provided_token = (request.headers.get("X-Active-Gala-Token") or "").strip()
    if not expected_token or provided_token != expected_token:
        return JsonResponse({"error": "forbidden"}, status=403)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        payload = {}

    wallet_uuid = (payload.get("wallet_uuid") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    start_return_url = (payload.get("start_return_url") or "").strip() or None
    if not wallet_uuid:
        return JsonResponse({"error": "wallet_uuid_required"}, status=400)

    wallet = Wallet.objects.filter(uuid=wallet_uuid).select_related("user").first()
    if not wallet or not wallet.user:
        return JsonResponse({"error": "wallet_not_found"}, status=404)
    if email and wallet.user.email.lower() != email:
        return JsonResponse({"error": "email_wallet_mismatch"}, status=400)

    context = _active_context_with_labels()
    place = Place.objects.filter(uuid=context.get("active_place_uuid")).first()
    asset = Asset.objects.filter(uuid=context.get("active_asset_uuid"), archive=False, category__in=MONETARY_CATEGORIES).first()
    if not place or not asset:
        return JsonResponse({"error": "active_context_invalid"}, status=409)

    try:
        add_metadata = {
            "active_place_uuid": str(place.uuid),
            "active_asset_uuid": str(asset.uuid),
            "lespass_uuid": str(place.uuid),
        }
        checkout_session = _create_stripe_checkout_for_selected_asset(
            user=wallet.user,
            asset=asset,
            place=place,
            add_metadata=add_metadata,
            start_return_url=start_return_url,
        )
        if not checkout_session:
            return JsonResponse({"error": "stripe_not_configured"}, status=417)
    except Exception as e:
        logger.exception("active_context_refill_checkout error")
        return JsonResponse({"error": "checkout_creation_failed", "detail": str(e)}, status=500)

    return JsonResponse({
        "checkout_url": checkout_session.url,
        "active_place_uuid": str(place.uuid),
        "active_place_name": place.name,
        "active_asset_uuid": str(asset.uuid),
        "active_asset_name": asset.name,
        "freeze_others": bool(context.get("freeze_others")),
    }, status=202)


@csrf_exempt
def active_context_retrieve_refill_checkout(request, pk=None):
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    expected_token = (os.environ.get("ACTIVE_GALA_API_TOKEN") or "").strip()
    provided_token = (request.headers.get("X-Active-Gala-Token") or "").strip()
    if not expected_token or provided_token != expected_token:
        return JsonResponse({"error": "forbidden"}, status=403)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        payload = {}

    wallet_uuid = (payload.get("wallet_uuid") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    if not wallet_uuid:
        return JsonResponse({"error": "wallet_uuid_required"}, status=400)

    wallet = Wallet.objects.filter(uuid=wallet_uuid).select_related("user").first()
    if not wallet or not wallet.user:
        return JsonResponse({"error": "wallet_not_found"}, status=404)
    if email and wallet.user.email and wallet.user.email.lower() != email:
        return JsonResponse({"error": "email_wallet_mismatch"}, status=400)

    checkout_db = CheckoutStripe.objects.filter(pk=pk).select_related("asset", "user").first()
    if not checkout_db:
        return JsonResponse({"error": "checkout_not_found"}, status=404)
    if checkout_db.user and checkout_db.user != wallet.user:
        return JsonResponse({"error": "checkout_user_mismatch"}, status=403)

    try:
        _validate_selected_asset_checkout_and_make_transaction(checkout_db, wallet)
    except Exception as e:
        logger.exception("active_context_retrieve_refill_checkout error")
        return JsonResponse({"error": "payment_validation_failed", "detail": str(e)}, status=400)

    user_token = Token.objects.filter(wallet=wallet, asset=checkout_db.asset).first()
    return JsonResponse({
        "status": "paid",
        "checkout_uuid": str(checkout_db.uuid),
        "wallet_uuid": str(wallet.uuid),
        "asset_uuid": str(checkout_db.asset.uuid),
        "asset_name": checkout_db.asset.name,
        "asset_balance_cents": int(user_token.value if user_token else 0),
    }, status=200)


def gala_create(request):
    if request.method != "POST":
        return redirect("/dashboard/")

    event_type = (request.POST.get("event_type") or "").strip()
    custom_event = (request.POST.get("custom_event") or "").strip()
    school_code = (request.POST.get("school_code") or "").strip()
    set_active = request.POST.get("set_active") == "on"

    event_label = custom_event if event_type == "custom" else event_type
    if not event_label:
        messages.error(request, "Événement invalide.")
        return redirect("/dashboard/")

    try:
        gala_id = _build_gala_identifier(event_label, school_code)
    except Exception:
        messages.error(request, "Impossible de construire l'identifiant gala.")
        return redirect("/dashboard/")

    active_place = Place.objects.filter(uuid=_read_active_context().get("active_place_uuid")).first() or Place.objects.first()
    if not active_place:
        messages.error(request, "Aucun lieu Fedow disponible.")
        return redirect("/dashboard/")

    gala_slug = _build_gala_domain_slug(gala_id)
    suggested_domain = f"{gala_slug}.cashless.galas-am-aix.rezal.fr"

    place = Place.objects.filter(name=gala_id).first()
    if not place:
        try:
            place_wallet = Wallet.objects.create(name=f"wallet_{gala_id}")
            place = Place.objects.create(
                name=gala_id,
                wallet=place_wallet,
                cashless_server_ip=active_place.cashless_server_ip,
                cashless_server_url=f"https://{suggested_domain}",
                lespass_domain=active_place.lespass_domain,
                stripe_connect_account=active_place.stripe_connect_account,
                stripe_connect_valid=active_place.stripe_connect_valid,
            )
            place.federations.set(active_place.federations.all())
        except Exception as e:
            messages.error(request, f"Création lieu gala impossible: {e}")
            return redirect("/dashboard/")

    asset_name = f"{gala_id} COIN"
    currency_code = (re.sub(r"[^A-Z0-9]", "", _normalize_gala_event(event_label))[:3] or "GAL")
    existing = Asset.objects.filter(name=asset_name, wallet_origin=place.wallet).first()
    if existing:
        asset = existing
    else:
        try:
            asset = asset_creator(
                name=asset_name,
                currency_code=currency_code,
                category=Asset.TOKEN_LOCAL_FIAT,
                wallet_origin=place.wallet,
            )
        except Exception as e:
            messages.error(request, f"Création monnaie gala impossible: {e}")
            return redirect("/dashboard/")

    if set_active:
        ctx = _read_active_context()
        _write_active_context({
            "active_place_uuid": str(place.uuid),
            "active_asset_uuid": str(asset.uuid),
            "freeze_others": ctx.get("freeze_others", True),
        })

    cmd = f"/home/ubuntu/TiBillet/tools/create_laboutik_instance.sh --gala-id '{gala_id}' --domain '{suggested_domain}'"

    req = {
        "created_at": timezone.localtime(timezone.now(), PARIS_TZ).isoformat(),
        "gala_id": gala_id,
        "event_label": event_label,
        "school_code": re.sub(r'[^0-9]', '', school_code) or _current_school_code(),
        "asset_uuid": str(asset.uuid),
        "asset_name": asset.name,
        "place_uuid": str(place.uuid),
        "place_name": place.name,
        "suggested_domain": suggested_domain,
        "command": cmd,
        "status": "pending_host_provision",
    }
    _append_provision_request(req)

    messages.success(
        request,
        f"Gala créé: {gala_id}. Monnaie: {asset.name}. "
        f"Provision LaBoutik automatique en cours (traitement chaque minute). "
        f"Commande de référence: {cmd}"
    )
    return redirect("/dashboard/")


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
    n = n.replace("’", "'")
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
        # Ignore l'ancien bar "Pian's"
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


def _create_stripe_checkout_for_wallet(wallet, email, asset, place, add_metadata=None, start_return_url=None):
    """Like _create_stripe_checkout_for_selected_asset but works with an ephemeral wallet (no Django user)."""
    config = Configuration.get_solo()
    if not config.get_stripe_api():
        return None

    stripe.api_key = config.get_stripe_api()
    source_wallet = config.primary_wallet if asset.category == Asset.STRIPE_FED_FIAT else asset.wallet_origin
    if not source_wallet:
        raise ValueError(f"Source wallet missing for asset {asset.uuid}")
    id_price_stripe = asset.get_id_price_stripe()
    if not id_price_stripe:
        raise ValueError(f"Stripe price missing for asset {asset.uuid}")

    primary_token, _ = Token.objects.get_or_create(wallet=source_wallet, asset=asset)
    user_token, _ = Token.objects.get_or_create(wallet=wallet, asset=asset)

    metadata = {
        "primary_token": f"{primary_token.uuid}",
        "user_token": f"{user_token.uuid}",
    }
    if add_metadata:
        metadata.update(add_metadata)

    signer = Signer()
    signed_data = signer.sign(dict_to_b64_utf8(metadata))
    checkout_db = CheckoutStripe.objects.create(asset=user_token.asset, user=None, metadata=signed_data)

    if not start_return_url:
        return_url = f"https://{place.lespass_domain}/recharge/{add_metadata.get('qrcode_uuid', '')}/return/{checkout_db.uuid}/"
    else:
        if not start_return_url.endswith("/"):
            start_return_url += "/"
        return_url = f"{start_return_url}{checkout_db.uuid}/"

    data_checkout = {
        "success_url": return_url,
        "cancel_url": return_url,
        "payment_method_types": ["card"],
        "line_items": [{"price": f"{id_price_stripe}", "quantity": 1}],
        "mode": "payment",
        "metadata": {"signed_data": f"{signed_data}"},
    }
    if email:
        data_checkout["customer_email"] = email

    checkout_session = stripe.checkout.Session.create(**data_checkout)
    checkout_db.checkout_session_id_stripe = checkout_session.id
    checkout_db.save(update_fields=["checkout_session_id_stripe"])
    return checkout_session


@csrf_exempt
def guest_refill_checkout(request):
    """Crée un checkout Stripe pour une carte par son qrcode_uuid, sans compte utilisateur."""
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    expected_token = (os.environ.get("ACTIVE_GALA_API_TOKEN") or "").strip()
    provided_token = (request.headers.get("X-Active-Gala-Token") or "").strip()
    if not expected_token or provided_token != expected_token:
        return JsonResponse({"error": "forbidden"}, status=403)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        payload = {}

    qrcode_uuid = (payload.get("qrcode_uuid") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    start_return_url = (payload.get("start_return_url") or "").strip() or None

    if not qrcode_uuid:
        return JsonResponse({"error": "qrcode_uuid_required"}, status=400)

    try:
        card = Card.objects.filter(qrcode_uuid=qrcode_uuid).first()
    except Exception:
        return JsonResponse({"error": "invalid_qrcode_uuid"}, status=400)

    if not card:
        return JsonResponse({"error": "card_not_found"}, status=404)

    wallet = card.get_wallet()
    if not wallet:
        return JsonResponse({"error": "wallet_unavailable"}, status=503)

    context = _active_context_with_labels()
    place = Place.objects.filter(uuid=context.get("active_place_uuid")).first()
    asset = Asset.objects.filter(
        uuid=context.get("active_asset_uuid"),
        archive=False,
        category__in=MONETARY_CATEGORIES,
    ).first()
    if not place or not asset:
        return JsonResponse({"error": "active_context_invalid"}, status=409)

    try:
        add_metadata = {
            "active_place_uuid": str(place.uuid),
            "active_asset_uuid": str(asset.uuid),
            "qrcode_uuid": str(qrcode_uuid),
        }
        checkout_session = _create_stripe_checkout_for_wallet(
            wallet=wallet,
            email=email,
            asset=asset,
            place=place,
            add_metadata=add_metadata,
            start_return_url=start_return_url,
        )
        if not checkout_session:
            return JsonResponse({"error": "stripe_not_configured"}, status=417)
    except Exception as e:
        logger.exception("guest_refill_checkout error")
        return JsonResponse({"error": "checkout_creation_failed", "detail": str(e)}, status=500)

    return JsonResponse({
        "checkout_url": checkout_session.url,
        "active_place_uuid": str(place.uuid),
        "active_place_name": place.name,
        "active_asset_uuid": str(asset.uuid),
        "active_asset_name": asset.name,
        "card_number": card.number_printed,
        "is_ephemere": card.is_wallet_ephemere(),
    }, status=202)


@csrf_exempt
def guest_retrieve_refill_checkout(request, pk=None):
    """Valide le paiement Stripe pour un recharge guest (sans compte utilisateur)."""
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    expected_token = (os.environ.get("ACTIVE_GALA_API_TOKEN") or "").strip()
    provided_token = (request.headers.get("X-Active-Gala-Token") or "").strip()
    if not expected_token or provided_token != expected_token:
        return JsonResponse({"error": "forbidden"}, status=403)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        payload = {}

    qrcode_uuid = (payload.get("qrcode_uuid") or "").strip()
    if not qrcode_uuid:
        return JsonResponse({"error": "qrcode_uuid_required"}, status=400)

    try:
        card = Card.objects.filter(qrcode_uuid=qrcode_uuid).first()
    except Exception:
        return JsonResponse({"error": "invalid_qrcode_uuid"}, status=400)

    if not card:
        return JsonResponse({"error": "card_not_found"}, status=404)

    wallet = card.get_wallet()
    if not wallet:
        return JsonResponse({"error": "wallet_unavailable"}, status=503)

    checkout_db = CheckoutStripe.objects.filter(pk=pk).select_related("asset").first()
    if not checkout_db:
        return JsonResponse({"error": "checkout_not_found"}, status=404)
    if checkout_db.user:
        return JsonResponse({"error": "checkout_belongs_to_user"}, status=403)

    try:
        _validate_selected_asset_checkout_and_make_transaction(checkout_db, wallet)
    except Exception as e:
        logger.exception("guest_retrieve_refill_checkout error")
        return JsonResponse({"error": "payment_validation_failed", "detail": str(e)}, status=400)

    user_token = Token.objects.filter(wallet=wallet, asset=checkout_db.asset).first()
    return JsonResponse({
        "status": "paid",
        "checkout_uuid": str(checkout_db.uuid),
        "wallet_uuid": str(wallet.uuid),
        "asset_uuid": str(checkout_db.asset.uuid),
        "asset_name": checkout_db.asset.name,
        "asset_balance_cents": int(user_token.value if user_token else 0),
        "card_number": card.number_printed,
        "is_ephemere": card.is_wallet_ephemere(),
    }, status=200)


def laboutik_delete(request):
    if request.method != "POST":
        return redirect("/dashboard/")

    instance_name = (request.POST.get("instance_name") or "").strip()
    confirm_name = (request.POST.get("confirm_name") or "").strip()
    admin_password = request.POST.get("admin_password") or ""

    if not request.user.check_password(admin_password):
        messages.error(request, "Mot de passe administrateur incorrect.")
        return redirect("/dashboard/")

    if instance_name != confirm_name:
        messages.error(request, "Le nom de confirmation ne correspond pas au nom de l'instance.")
        return redirect("/dashboard/")

    if not re.fullmatch(r"Laboutik_[a-z0-9\-]+", instance_name):
        messages.error(request, f"Nom d'instance invalide : {instance_name}")
        return redirect("/dashboard/")

    instance_path = os.path.join(LABOUTIK_ROOT, instance_name)
    if not os.path.isdir(instance_path):
        messages.error(request, f"Instance introuvable : {instance_name}")
        return redirect("/dashboard/")

    existing = [r for r in _read_delete_requests()
                if r.get("instance_name") == instance_name and r.get("status") in ("pending", "processing")]
    if existing:
        messages.warning(request, f"Suppression de {instance_name} déjà en cours.")
        return redirect("/dashboard/")

    slug = instance_name[len("Laboutik_"):]
    req = {
        "instance_name": instance_name,
        "slug": slug,
        "project_name": f"laboutik_{slug}",
        "requested_at": timezone.localtime(timezone.now(), PARIS_TZ).isoformat(),
        "requested_by": str(request.user),
        "status": "pending",
    }
    _append_delete_request(req)
    logger.info(f"laboutik_delete: suppression demandée pour {instance_name} par {request.user}")
    messages.success(
        request,
        f"Suppression de {instance_name} en attente de traitement (< 1 min). "
        f"Rafraîchissez la page pour voir le résultat."
    )
    return redirect("/dashboard/")
