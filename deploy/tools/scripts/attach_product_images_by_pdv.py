import argparse
import os
import re
from pathlib import Path

import django
import requests
from django.core.files.base import ContentFile

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Cashless.settings")
django.setup()

from APIcashless.models import PointDeVente

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
TIMEOUT = 20
HEADERS = {"User-Agent": "TiBilletOps/1.0 (cashless image import)"}

CATEGORY_FALLBACK = {
    "bières": "beer glass drink",
    "cocktails": "cocktail drink glass",
    "softs": "soft drink beverage",
    "vins": "wine glass drink",
}

PRODUCT_QUERY_OVERRIDES = {
    "coca-cola": ["coca cola can", "coca cola beverage", "cola drink can"],
    "quillons": ["shot glass", "liquor shot", "party shot drink"],
}


def clean_name(name):
    n = (name or "").strip()
    n = re.sub(r"^[^\w]+\s*", "", n)
    n = re.sub(r"\([^)]*\)", "", n)
    n = re.sub(r"\b\d+\s*cl\b", "", n, flags=re.IGNORECASE)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def commons_search_image_urls(query, limit=12):
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,
        "gsrlimit": limit,
        "prop": "imageinfo",
        "iiprop": "url|mime",
        "iiurlwidth": 1200,
        "format": "json",
        "formatversion": 2,
    }
    resp = requests.get(COMMONS_API, params=params, timeout=TIMEOUT, headers=HEADERS)
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", [])
    urls = []
    for page in pages:
        info = (page.get("imageinfo") or [{}])[0]
        mime = (info.get("mime") or "").lower()
        if mime in ("image/jpeg", "image/jpg", "image/png", "image/webp"):
            u = info.get("thumburl") or info.get("url")
            if u:
                urls.append(u)
    return urls


def guess_ext(url):
    suffix = Path(url.split("?")[0]).suffix.lower().strip(".")
    return suffix if suffix in ("jpg", "jpeg", "png", "webp") else "jpg"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdv", required=True, help="Nom exact du point de vente")
    parser.add_argument("--force", action="store_true", help="Remplace aussi les images existantes")
    args = parser.parse_args()

    pdv = PointDeVente.objects.get(name=args.pdv)
    results = []

    for art in pdv.articles.filter(archive=False).select_related("categorie").order_by("name"):
        if art.image and not args.force:
            results.append((art.name, "SKIP_ALREADY_SET", None))
            continue

        cat = (art.categorie.name if art.categorie else "").strip().lower()
        product_q = clean_name(art.name)

        queries = [
            f"{product_q} drink",
            product_q,
            CATEGORY_FALLBACK.get(cat, "beverage drink"),
        ]
        key = clean_name(art.name).lower().replace("é", "e")
        for token, extra_queries in PRODUCT_QUERY_OVERRIDES.items():
            if token in key:
                queries = extra_queries + queries
                break

        image_bytes = None
        final_url = None
        used_query = None
        for query in queries:
            try:
                for candidate_url in commons_search_image_urls(query):
                    try:
                        img = requests.get(candidate_url, timeout=TIMEOUT, headers=HEADERS)
                        img.raise_for_status()
                        image_bytes = img.content
                        final_url = candidate_url
                        used_query = query
                        break
                    except Exception:
                        continue
                if image_bytes:
                    break
            except Exception:
                continue

        if not image_bytes:
            results.append((art.name, "NO_IMAGE", None))
            continue

        ext = guess_ext(final_url)
        base = re.sub(r"[^a-z0-9]+", "-", clean_name(art.name).lower()).strip("-") or f"article-{art.pk}"
        filename = f"{base}.{ext if ext != 'jpeg' else 'jpg'}"
        art.image.save(filename, ContentFile(image_bytes), save=True)
        results.append((art.name, "OK", used_query))

    print(f"UPDATED_RESULTS {args.pdv}")
    for row in results:
        print(row)


if __name__ == "__main__":
    main()
