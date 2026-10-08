"""Shared validation of private, immutable native Fedow card CSV lots.

The release contains metadata only. Actual QR/NFC associations stay in private
S3 objects named by their byte checksum, outside Git and public source offers.
"""

import csv
import hashlib
import io
import json
import re
from urllib.parse import urlsplit
from uuid import UUID


EMPTY_STOCK = {"schema_version": 1, "lots": []}
MAX_CSV_BYTES = 10 * 1024 * 1024


def smoke_release_id(commit, stock):
    """Same code with different uploaded lots must have a different proof."""
    validate_catalogue(stock)
    suffix = ''
    if stock['lots']:
        encoded = json.dumps(stock, sort_keys=True, separators=(',', ':')).encode()
        suffix = '-' + hashlib.sha256(encoded).hexdigest()
    return 'smoke-' + commit + suffix


def validate_catalogue(stock):
    if not isinstance(stock, dict) or set(stock) != {"schema_version", "lots"}:
        raise ValueError("card_stock must contain schema_version and lots")
    if type(stock["schema_version"]) is not int or stock["schema_version"] != 1:
        raise ValueError("unsupported card_stock schema")
    if not isinstance(stock["lots"], list) or len(stock["lots"]) > 100:
        raise ValueError("card_stock lots must be a list of at most 100 lots")
    seen = set()
    for lot in stock["lots"]:
        if not isinstance(lot, dict) or set(lot) != {"key", "sha256", "rows", "generation"}:
            raise ValueError("card_stock lot must contain key, sha256, rows and generation")
        digest = lot["sha256"]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("card_stock lot sha256 is invalid")
        if lot["key"] != f"card-stock/{digest}.csv":
            raise ValueError("card_stock key must be its checksum under card-stock/")
        if type(lot["rows"]) is not int or not 1 <= lot["rows"] <= 100000:
            raise ValueError("card_stock rows must be between 1 and 100000")
        if type(lot["generation"]) is not int or not 1 <= lot["generation"] <= 2147483647:
            raise ValueError("card_stock generation must be a positive 32-bit integer")
        if digest in seen:
            raise ValueError("duplicate card_stock lot")
        seen.add(digest)
    return stock


def read_cards(data, domain):
    if not data or len(data) > MAX_CSV_BYTES:
        raise ValueError("card CSV must be nonempty and at most 10 MiB")
    records = []
    try:
        reader = csv.reader(io.StringIO(data.decode("utf-8")), strict=True)
        for line, values in enumerate(reader, 1):
            if len(values) != 3:
                raise ValueError(f"card CSV line {line}: expected three columns, without header")
            url, number, tag = values
            parsed = urlsplit(url)
            if (parsed.scheme != "https" or parsed.netloc != domain
                    or parsed.query or parsed.fragment or not parsed.path.startswith("/qr/")):
                raise ValueError(f"card CSV line {line}: QR must use https://{domain}/qr/<uuid>")
            try:
                qr = UUID(parsed.path[4:])
            except ValueError as error:
                raise ValueError(f"card CSV line {line}: invalid QR UUID") from error
            if parsed.path != "/qr/" + str(qr):
                raise ValueError(f"card CSV line {line}: QR must use a canonical UUID")
            if not re.fullmatch(r"[A-Z0-9]{8}", number):
                raise ValueError(f"card CSV line {line}: printed number must be eight uppercase characters")
            if not re.fullmatch(r"[A-F0-9]{8}", tag):
                raise ValueError(f"card CSV line {line}: NFC must be eight uppercase hex characters")
            records.append((url, number, tag))
    except (UnicodeDecodeError, csv.Error) as error:
        raise ValueError("card CSV must be valid UTF-8 comma-separated text") from error
    validate_unique([{"cards": records}])
    return records


def validate_unique(lots):
    seen = [set(), set(), set()]
    for lot in lots:
        for url, number, tag in lot["cards"]:
            identifiers = (str(UUID(url.partition("/qr/")[2])), number, tag)
            for field, value in enumerate(identifiers):
                if value in seen[field]:
                    raise ValueError("duplicate QR, printed number or NFC in card stock")
                seen[field].add(value)


def verified_cards(data, lot, domain):
    if hashlib.sha256(data).hexdigest() != lot["sha256"]:
        raise ValueError("card_stock CSV checksum mismatch")
    cards = read_cards(data, domain)
    if len(cards) != lot["rows"]:
        raise ValueError("card_stock CSV row count mismatch")
    return cards
