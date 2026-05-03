#!/usr/bin/env python3
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REQUESTS_PATH = Path('/home/ubuntu/TiBillet/Fedow/www/gala_provision_requests.json')
SCRIPT_PATH = Path('/home/ubuntu/TiBillet/tools/create_laboutik_instance.sh')


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat()


def load_items():
    if not REQUESTS_PATH.exists():
        return []
    try:
        return json.loads(REQUESTS_PATH.read_text(encoding='utf-8'))
    except Exception:
        return []


def save_items(items):
    REQUESTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    REQUESTS_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')


def run_one(item):
    gala_id = (item.get('gala_id') or '').strip()
    domain = (item.get('suggested_domain') or '').strip()
    if not gala_id or not domain:
        raise RuntimeError('missing gala_id/domain in request')

    cmd = [str(SCRIPT_PATH), '--gala-id', gala_id, '--domain', domain]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or 'provision failed').strip())
    return (proc.stdout or '').strip()


def main():
    items = load_items()
    if not isinstance(items, list) or not items:
        return

    changed = False
    for item in items:
        if item.get('status') != 'pending_host_provision':
            continue
        changed = True
        item['status'] = 'provisioning'
        item['started_at'] = now_iso()
        save_items(items)
        try:
            out = run_one(item)
            item['status'] = 'provisioned'
            item['finished_at'] = now_iso()
            item['provision_log'] = out[-3000:]
        except Exception as e:
            item['status'] = 'error'
            item['finished_at'] = now_iso()
            item['error'] = str(e)
        save_items(items)

    if changed:
        save_items(items)


if __name__ == '__main__':
    main()
