#!/usr/bin/env python3
"""
Processes pending Laboutik instance deletion requests written by the Fedow dashboard.
Run via crontab every minute as ubuntu user.
"""
import json
import logging
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REQUESTS_PATH = Path('/home/ubuntu/TiBillet/Fedow/www/laboutik_delete_requests.json')
LABOUTIK_ROOT = Path('/home/ubuntu/TiBillet')
LOG_PATH = Path('/home/ubuntu/TiBillet/Fedow/www/laboutik_delete_requests.log')

logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)
logger = logging.getLogger(__name__)


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


def delete_instance(item):
    instance_name = item['instance_name']
    project_name = item['project_name']
    instance_path = LABOUTIK_ROOT / instance_name

    if not instance_path.is_dir():
        logger.info(f"{instance_name}: directory already gone, nothing to do")
        return

    logger.info(f"{instance_name}: running docker compose down")
    try:
        result = subprocess.run(
            ['docker', 'compose', '--project-name', project_name,
             'down', '-v', '--remove-orphans'],
            cwd=str(instance_path),
            capture_output=True, text=True, timeout=120
        )
        logger.info(f"{instance_name}: docker compose down exit={result.returncode} "
                    f"stdout={result.stdout[:500]} stderr={result.stderr[:500]}")
    except Exception as e:
        logger.error(f"{instance_name}: docker compose down exception: {e}")

    logger.info(f"{instance_name}: removing directory {instance_path}")
    shutil.rmtree(str(instance_path))
    logger.info(f"{instance_name}: deleted successfully")


def main():
    items = load_items()
    if not isinstance(items, list) or not items:
        return

    changed = False
    for item in items:
        if item.get('status') != 'pending':
            continue
        changed = True
        item['status'] = 'processing'
        item['started_at'] = now_iso()
        save_items(items)
        try:
            delete_instance(item)
            item['status'] = 'done'
            item['finished_at'] = now_iso()
            logger.info(f"{item['instance_name']}: status → done")
        except Exception as e:
            item['status'] = 'error'
            item['finished_at'] = now_iso()
            item['error'] = str(e)
            logger.error(f"{item['instance_name']}: error: {e}")
        save_items(items)

    if changed:
        save_items(items)


if __name__ == '__main__':
    main()
