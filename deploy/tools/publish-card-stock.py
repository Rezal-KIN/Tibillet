#!/usr/bin/env python3
"""Validate native CSV lots, publish private immutable objects, write metadata.

Use only after confirming the NFC byte order with the event's physical reader.
Publishing does not import cards or switch traffic. Commit the output catalogue
to deploy/card-stock.json to select these exact lots in the Test pipeline.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent / 'runtime'))
from card_stock import read_cards, validate_catalogue, validate_unique


def publish(aws, bucket, lot, path):
    result = subprocess.run(aws + ['s3api', 'put-object', '--bucket', bucket,
        '--key', lot['key'], '--body', str(path), '--if-none-match', '*'],
        text=True, capture_output=True, timeout=120)
    if result.returncode:
        if 'PreconditionFailed' not in result.stderr and '412' not in result.stderr:
            raise RuntimeError('private card CSV upload failed')
        with tempfile.TemporaryDirectory(prefix='verify-card-stock-') as directory:
            prior = Path(directory) / 'prior.csv'
            subprocess.run(aws + ['s3', 'cp', '--only-show-errors',
                f"s3://{bucket}/{lot['key']}", str(prior)],
                check=True, capture_output=True, timeout=120)
            if prior.read_bytes() != path.read_bytes():
                raise ValueError('immutable card CSV already contains different bytes')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lot', nargs=2, action='append', required=True,
                        metavar=('GENERATION', 'CSV'))
    parser.add_argument('--domain', required=True)
    parser.add_argument('--bucket', required=True)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--region', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    aws = ['aws', '--profile', args.profile, '--region', args.region]
    identity = subprocess.run(aws + ['sts', 'get-caller-identity', '--output', 'json'],
                              check=True, capture_output=True, text=True, timeout=60)
    if json.loads(identity.stdout)['Account'] != '318629836660':
        raise ValueError('wrong Gala AWS account')
    lots = []
    # Snapshot inputs once: metadata, validation and upload use identical bytes.
    with tempfile.TemporaryDirectory(prefix='publish-card-stock-') as directory:
        paths = []
        for index, (generation, source) in enumerate(args.lot):
            data = Path(source).read_bytes()
            cards = read_cards(data, args.domain)
            digest = hashlib.sha256(data).hexdigest()
            lots.append({'key': f'card-stock/{digest}.csv', 'sha256': digest,
                         'rows': len(cards), 'generation': int(generation), 'cards': cards})
            path = Path(directory) / f'{index}.csv'
            path.write_bytes(data)
            paths.append(path)
        validate_unique(lots)
        catalogue = {'schema_version': 1,
                     'lots': [{key: value for key, value in lot.items() if key != 'cards'} for lot in lots]}
        validate_catalogue(catalogue)
        for lot, path in zip(catalogue['lots'], paths):
            publish(aws, args.bucket, lot, path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
            dir=args.output.parent, prefix='.card-stock-', delete=False) as output:
        temp = Path(output.name)
        json.dump(catalogue, output, indent=2, sort_keys=True)
        output.write('\n')
    try:
        os.replace(temp, args.output)
    finally:
        temp.unlink(missing_ok=True)
    print(f"Private stock published: {len(lots)} lots, {sum(lot['rows'] for lot in lots)} cards")
    print(f'Catalogue metadata written: {args.output}')


if __name__ == '__main__':
    main()
