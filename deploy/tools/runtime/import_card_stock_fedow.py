"""Deployment wrapper executed through Django shell; native importer unchanged.

No file is mounted over application code. This function only selects absent
rows, answers the native command's prompts and verifies the result atomically.
"""

import contextlib
import csv
import io
from pathlib import Path
import tempfile
from unittest.mock import patch
from uuid import UUID

from django.core.management import call_command
from django.db import transaction
from django.db.models import Q
from fedow_core.models import Card, Place


def existing_cards(cards):
    """Bound IN queries for SQLite, without loading wallets or making writes."""
    by_identity = [{}, {}, {}]
    for offset in range(0, len(cards), 200):
        chunk = cards[offset:offset + 200]
        rows = Card.objects.filter(
            Q(qrcode_uuid__in=[UUID(row[0].partition('/qr/')[2]) for row in chunk])
            | Q(number_printed__in=[row[1] for row in chunk])
            | Q(first_tag_id__in=[row[2] for row in chunk])
        ).values('qrcode_uuid', 'number_printed', 'first_tag_id',
                 'origin__place_id', 'origin__generation')
        for row in rows:
            identity = (str(row['qrcode_uuid']), row['number_printed'], row['first_tag_id'])
            for field, value in enumerate(identity):
                by_identity[field][value] = (identity, row)
    return by_identity


def classify(cards, indexes):
    missing = []
    for url, number, tag in cards:
        identity = (str(UUID(url.partition('/qr/')[2])), number, tag)
        matches = [index.get(value) for index, value in zip(indexes, identity)]
        if all(match is None for match in matches):
            missing.append((url, number, tag))
        elif any(match is None or match[0] != identity for match in matches):
            # Printed number locates the physical card, without logging NFCs.
            raise ValueError(f'card stock conflicts with Fedow: printed number {number}')
    return missing


def import_stock(identity, domain, lots, check=False):
    all_cards = [row for lot in lots for row in lot['cards']]
    with transaction.atomic():
        place = Place.objects.select_for_update().get(
            uuid=identity['place_uuid'], wallet_id=identity['wallet_uuid'], lespass_domain=domain)
        places = list(Place.objects.all())
        if sum(other.name == place.name for other in places) != 1:
            raise ValueError('native importer requires a unique paired place name')
        place_index = next(index for index, other in enumerate(places) if other.pk == place.pk)
        indexes = existing_cards(all_cards)
        # Detect conflicts throughout the catalogue before the first import.
        pending = [(lot, classify(lot['cards'], indexes)) for lot in lots]
        added = 0
        for lot, missing in pending:
            if not missing:
                continue
            if check:
                raise ValueError('card stock is incomplete in Fedow')
            with tempfile.TemporaryDirectory(prefix='gala-card-stock-') as directory:
                path = Path(directory) / 'missing.csv'
                with path.open('w', encoding='utf-8', newline='') as stream:
                    csv.writer(stream).writerows(missing)
                responses = iter([
                    ('path fichier csv ? \n', str(path)),
                    ('\nnumber ? \n', str(place_index)),
                    ('\nEnter a generation number \n', str(lot['generation'])),
                ])

                def answer(prompt):
                    expected, value = next(responses)
                    if prompt != expected:
                        raise ValueError('native import_cards prompt changed; review the pinned image')
                    return value

                # The upstream command prints every NFC/QR; keep stock out of
                # pipeline logs. Exceptions still propagate and roll back.
                with patch('builtins.input', answer), contextlib.redirect_stdout(io.StringIO()):
                    call_command('import_cards')
                if next(responses, None) is not None:
                    raise ValueError('native import_cards did not consume its expected prompts')
            imported = existing_cards(missing)
            if classify(missing, imported):
                raise ValueError('native import_cards left missing cards')
            for url, _, _ in missing:
                row = imported[0][str(UUID(url.partition('/qr/')[2]))][1]
                if (str(row['origin__place_id']) != str(place.pk)
                        or row['origin__generation'] != lot['generation']):
                    raise ValueError('native import_cards selected a different origin; rolled back')
            added += len(missing)
        if classify(all_cards, existing_cards(all_cards)):
            raise ValueError('card stock post-import verification failed')
    return {'status': 'ready', 'expected': len(all_cards), 'created': added,
            'existing': len(all_cards) - added, 'lots': len(lots)}
