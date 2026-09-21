import re
from pathlib import Path

import requests
from django.core.files.base import ContentFile
from APIcashless.models import PointDeVente

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
TIMEOUT = 20
CATEGORY_FALLBACK = {
    "bières": "beer glass drink",
    "cocktails": "cocktail drink glass",
    "softs": "soft drink beverage",
    "vins": "wine glass drink",
}


def clean_name(name):
    n = (name or "").strip()
    n = re.sub(r"^[^\w]+\s*", "", n)
    n = re.sub(r"\([^)]*\)", "", n)
    n = re.sub(r"\b\d+\s*cl\b", "", n, flags=re.IGNORECASE)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def commons_search_image_url(query):
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,
        "gsrlimit": 6,
        "prop": "imageinfo",
        "iiprop": "url|mime",
        "iiurlwidth": 800,
        "format": "json",
        "formatversion": 2,
    }
    resp = requests.get(COMMONS_API, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", [])
    for page in pages:
        info = (page.get("imageinfo") or [{}])[0]
        mime = (info.get("mime") or "").lower()
        if mime in ("image/jpeg", "image/jpg", "image/png", "image/webp"):
            return info.get("thumburl") or info.get("url")
    return None


def guess_ext(content_type, url):
    ct = (content_type or "").lower()
    if "jpeg" in ct or "jpg" in ct:
        return "jpg"
    if "png" in ct:
        return "png"
    if "webp" in ct:
        return "webp"
    suffix = Path(url.split("?")[0]).suffix.lower().strip(".")
    return suffix if suffix in ("jpg", "jpeg", "png", "webp") else "jpg"


pdv = PointDeVente.objects.get(name="PIAN'S")
results = []

for art in pdv.articles.filter(archive=False).select_related("categorie").order_by("name"):
    cat = (art.categorie.name if art.categorie else "").strip().lower()
    product_q = clean_name(art.name)

    queries = [
        f"{product_q} drink",
        product_q,
        CATEGORY_FALLBACK.get(cat, "beverage drink"),
    ]

    image_url = None
    used_query = None
    for query in queries:
        try:
            image_url = commons_search_image_url(query)
            if image_url:
                used_query = query
                break
        except Exception:
            continue

    if not image_url:
        results.append((art.name, "NO_IMAGE", None))
        continue

    try:
        img = requests.get(image_url, timeout=TIMEOUT)
        img.raise_for_status()
        ext = guess_ext(img.headers.get("Content-Type"), image_url)
        base = re.sub(r"[^a-z0-9]+", "-", clean_name(art.name).lower()).strip("-") or f"article-{art.pk}"
        filename = f"{base}.{ext if ext != 'jpeg' else 'jpg'}"
        art.image.save(filename, ContentFile(img.content), save=True)
        results.append((art.name, "OK", used_query))
    except Exception as exc:
        results.append((art.name, f"ERR:{exc.__class__.__name__}", used_query))

print("UPDATED_RESULTS")
for row in results:
    print(row)
