#!/usr/bin/env python3
"""Record the operator's time-limited decision for one exact release, without a backup."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time


def manifest_digest(manifest):
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def approval_path(root, gala, digest):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,62}', gala) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('invalid exact release identity')
    return root / gala / 'backup-exceptions' / (digest + '.json')


def grant(root, gala, digest, expires, reason, now=None):
    now = int(time.time()) if now is None else now
    if not now < expires <= now + 86400 or not 1 <= len(reason) <= 500:
        raise ValueError('an explicit reason and expiry within 24 hours are required')
    path = approval_path(root, gala, digest)
    path.parent.mkdir(parents=True, mode=0o750, exist_ok=True)
    if path.parent.is_symlink():
        raise ValueError('approval directory cannot be a symlink')
    record = {'schema_version': 1, 'gala_slug': gala, 'manifest_sha256': digest,
              'approved_at': now, 'expires_at': expires, 'reason': reason}
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        json.dump(record, output, sort_keys=True)
    return path


def permitted(root, gala, manifest, now=None):
    now = int(time.time()) if now is None else now
    if manifest.get('gala_slug') != gala:
        return False
    digest = manifest_digest(manifest)
    path = approval_path(root, gala, digest)
    try:
        info = path.lstat()
        # Deployments run as root; local QA runs with its own isolated UID.
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or path.parent.is_symlink()):
            return False
        data = json.loads(path.read_text())
        return (set(data) == {'schema_version', 'gala_slug', 'manifest_sha256', 'approved_at', 'expires_at', 'reason'}
                and type(data['schema_version']) is int and data['schema_version'] == 1
                and data['gala_slug'] == gala and data['manifest_sha256'] == digest
                and type(data['approved_at']) is int and type(data['expires_at']) is int
                and data['approved_at'] <= now < data['expires_at'] <= data['approved_at'] + 86400
                and isinstance(data['reason'], str) and 1 <= len(data['reason']) <= 500)
    except (OSError, ValueError, TypeError, KeyError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['grant', 'check'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--gala', required=True)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--manifest-sha256')
    parser.add_argument('--expires-at', type=int)
    parser.add_argument('--reason')
    args = parser.parse_args()
    if args.operation == 'grant':
        if not args.manifest_sha256 or args.expires_at is None or not args.reason:
            parser.error('grant requires the approved digest, expiration and reason')
        grant(args.root, args.gala, args.manifest_sha256, args.expires_at, args.reason)
    else:
        if not args.manifest or not permitted(args.root, args.gala, json.loads(args.manifest.read_text())):
            raise SystemExit(1)
    print('Explicit no-new-backup decision verified for exact release: ' + args.gala)


if __name__ == '__main__':
    main()
