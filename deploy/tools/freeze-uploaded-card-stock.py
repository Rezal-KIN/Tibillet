#!/usr/bin/env python3
"""Freeze native CSVs from private S3 upload folders into a release catalogue.

Upload to card-stock/uploads/<generation>/<name>.csv in the S3 console, then
run Test. No running Gala is modified by uploading a file. Production consumes
only the exact checksum-addressed catalogue successfully deployed on Smoke.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent / 'runtime'))
from card_stock import MAX_CSV_BYTES, read_cards, validate_catalogue, validate_unique

PREFIX = 'card-stock/uploads/'


def select(objects):
    selected = []
    for obj in objects:
        key = obj['Key']
        if key.endswith('/') and obj['Size'] == 0:
            continue  # S3 console folder markers
        match = re.fullmatch(re.escape(PREFIX) + r'([1-9][0-9]*)/[^/]+\.csv', key)
        if not match or not 1 <= int(match[1]) <= 2147483647:
            raise ValueError('upload folder requires <positive generation>/<name>.csv')
        if not 0 < obj['Size'] <= MAX_CSV_BYTES or not obj.get('ETag'):
            raise ValueError('uploaded card CSV must be nonempty and at most 10 MiB')
        selected.append((int(match[1]), key, obj['ETag']))
    if not 1 <= len(selected) <= 100:
        raise ValueError('upload folder must contain between 1 and 100 CSV lots')
    return sorted(selected)


def freeze(aws, bucket, domain, output):
    listing = subprocess.run(aws + ['s3api', 'list-objects-v2', '--bucket', bucket,
        '--prefix', PREFIX, '--output', 'json'], check=True, capture_output=True, text=True, timeout=120)
    selected = select(json.loads(listing.stdout).get('Contents', []))
    spec = importlib.util.spec_from_file_location('stock_publisher', Path(__file__).with_name('publish-card-stock.py'))
    publisher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publisher)
    with tempfile.TemporaryDirectory(prefix='freeze-card-stock-') as directory:
        lots, paths = [], []
        for index, (generation, key, etag) in enumerate(selected):
            path = Path(directory) / f'{index}.csv'
            # Refuse a concurrent replacement. The validated downloaded bytes
            # alone are used for the immutable publication and checksum.
            subprocess.run(aws + ['s3api', 'get-object', '--bucket', bucket,
                '--key', key, '--if-match', etag, str(path)],
                check=True, capture_output=True, text=True, timeout=120)
            data = path.read_bytes()
            cards = read_cards(data, domain)
            digest = hashlib.sha256(data).hexdigest()
            lots.append({'key': f'card-stock/{digest}.csv', 'sha256': digest,
                         'rows': len(cards), 'generation': generation, 'cards': cards})
            paths.append(path)
        validate_unique(lots)
        catalogue = validate_catalogue({'schema_version': 1,
            'lots': [{k: v for k, v in lot.items() if k != 'cards'} for lot in lots]})
        for lot, path in zip(catalogue['lots'], paths):
            publisher.publish(aws, bucket, lot, path)
    output.write_text(json.dumps(catalogue, indent=2, sort_keys=True) + '\n')
    print(f"Uploaded stock frozen: {len(lots)} lots, {sum(lot['rows'] for lot in lots)} cards")
    return catalogue


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bucket', required=True)
    parser.add_argument('--domain', default='galas-am-aix.rezal.fr')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    freeze(['aws', '--region', 'eu-west-3'], args.bucket, args.domain, args.output)


if __name__ == '__main__':
    main()
