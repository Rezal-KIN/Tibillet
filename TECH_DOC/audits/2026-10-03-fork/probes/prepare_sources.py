"""Materialize and checksum the exact public reference sources used by this audit."""
import argparse
import hashlib
import io
import json
import tarfile
import urllib.request
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--destination',type=Path,required=True)
args=parser.parse_args()
spec=json.loads((Path(__file__).resolve().parents[1]/'comparison.json').read_text())['overlays_reference']
args.destination.mkdir(parents=True,exist_ok=True)
for component in ('fedow','laboutik'):
    item=spec[component]
    archive=args.destination/(item['repository'].replace('/','-')+'-'+item['commit']+'.tar.gz')
    if not archive.exists():
        url=f"https://codeload.github.com/{item['repository']}/tar.gz/{item['commit']}"
        with urllib.request.urlopen(url,timeout=30) as response: archive.write_bytes(response.read())
    data=archive.read_bytes()
    if hashlib.sha256(data).hexdigest()!=item['archive_sha256']:
        raise ValueError(f'Archive checksum mismatch for {component}')
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for member in tar.getmembers():
            if not member.isfile(): continue
            rel=Path(*Path(member.name).parts[1:])
            if rel.is_absolute() or '..' in rel.parts: raise ValueError('Unsafe path')
            dest=args.destination/component/rel
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(tar.extractfile(member).read())
    print(component, item['commit'], 'checksum OK')
