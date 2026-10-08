#!/usr/bin/env python3
"""Download frozen private card lots and invoke Fedow's native importer."""

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

from card_stock import EMPTY_STOCK, validate_catalogue, validate_unique, verified_cards


def load_lots(stock, bucket, region, domain):
    validate_catalogue(stock)
    lots = []
    with tempfile.TemporaryDirectory(prefix='gala-card-stock-') as directory:
        for index, lot in enumerate(stock['lots']):
            path = Path(directory) / f'{index}.csv'
            subprocess.run(['aws', 's3', 'cp', '--only-show-errors',
                            f"s3://{bucket}/{lot['key']}", str(path), '--region', region],
                           check=True, capture_output=True, text=True, timeout=120)
            lots.append({**lot, 'cards': verified_cards(path.read_bytes(), lot, domain)})
    validate_unique(lots)
    return lots


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--bucket', required=True)
    parser.add_argument('--region', required=True)
    parser.add_argument('--domain', required=True)
    parser.add_argument('--check', action='store_true', help='Verify without importing')
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    # Historic manifests have no catalogue; they remain valid for rollback.
    stock = validate_catalogue(manifest.get('card_stock', EMPTY_STOCK))
    if not stock['lots']:
        print(json.dumps({'status': 'no-stock-configured', 'lots': 0}))
        return
    lots = load_lots(stock, args.bucket, args.region, args.domain)
    runtime = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location('refill_domain', runtime / 'configure-gala-refill-domain.py')
    refill = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(refill)
    identity = refill.django_shell('lespass', refill.lespass_code(args.domain))
    worker = (runtime / 'import_card_stock_fedow.py').read_text(encoding='utf-8')
    code = ("exec(compile(%r, 'import_card_stock_fedow.py', 'exec'))\n" % worker
            + "import json\nprint(json.dumps(import_stock(%r, %r, %r, check=%r)))\n"
            % (identity, args.domain, lots, args.check))
    result = subprocess.run(
        ['docker', 'exec', '-i', '-w', '/home/fedow/Fedow', 'fedow_django',
         'poetry', 'run', 'python', 'manage.py', 'shell'],
        input=code, text=True, capture_output=True, timeout=600,
    )
    if result.returncode:
        # Emit the final exception only, without echoing stock or shell source.
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else 'no error detail'
        raise RuntimeError('native Fedow card import failed: ' + detail)
    receipt = json.loads(result.stdout.strip().splitlines()[-1])
    if receipt.get('status') != 'ready' or receipt.get('expected') != sum(lot['rows'] for lot in lots):
        raise ValueError('invalid Fedow card import receipt')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
