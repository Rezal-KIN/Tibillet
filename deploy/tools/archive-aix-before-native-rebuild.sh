#!/usr/bin/env bash
# One-time, user-authorized native rebuild. Run only on inactive Gala Aix via
# SSM after checking its AWS instance ID and shared EIP association.
# Archives data and credentials; never deletes or rewrites a database.
set -euo pipefail
umask 077

case "${1:-}" in
  --check|--archive-three-databases) ;;
  *) echo 'Use --check or explicit --archive-three-databases' >&2; exit 1 ;;
esac
CONFIG=/etc/tibillet-gala/gala-am-aix.conf
# shellcheck source=/dev/null
source "$CONFIG"
[[ "$GALA_SLUG" == gala-am-aix && "$REPO_ROOT" == /opt/tibillet-gala/repository \
   && "$AWS_REGION" == eu-west-3 ]] || exit 1
RUNTIME=/var/lib/tibillet-gala/gala-am-aix
APP_COMMIT=60147839fd529828b00948b1179e0fa4924ac3d1
[[ ! -e "$RUNTIME/native-rebuild-prepared.json" \
   && ! -e "$RUNTIME/fedow-sqlite-storage.json" \
   && ! -e "$REPO_ROOT/deploy/Fedow/sqlite-database/db.sqlite3" ]] || {
  echo 'Existing native preparation/storage requires inspection; refusing replay' >&2; exit 1;
}

# Check every storage path before stopping anything. Reject unexpected mounts,
# symlinks and a different legacy checkout rather than adopting unknown data.
python3 - "$REPO_ROOT" <<'PY'
import json,subprocess,sys
from pathlib import Path
root=Path(sys.argv[1])
assert subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip() == '3cfd531b4ca3c9953f27ca06b2391cadcf33db00'
changed=set(subprocess.check_output(['git','-C',str(root),'diff','--name-only'],text=True).splitlines())
assert changed <= {'deploy/Lespass/www/static/reunion/css/tibillet.css','deploy/Lespass/www/static/reunion/js/membership-form.mjs'}
for name,folder,suffix in [('fedow_postgres','Fedow',''),('lespass_postgres','Lespass',''),('laboutik_postgres','Laboutik','/data')]:
    data=root/'deploy'/folder/'database'
    assert data.is_dir() and not data.is_symlink()
    container=json.loads(subprocess.check_output(['docker','inspect',name],text=True))[0]
    assert container['State']['Running']
    mounts=[m for m in container['Mounts'] if m['Destination']=='/var/lib/postgresql/data']
    assert len(mounts)==1 and mounts[0]['Source']==str(data)+suffix
PY
if [[ "$1" == --check ]]; then
  echo 'Legacy Aix archive preconditions validated; no database changed'
  exit 0
fi

# Freeze writers while the three PostgreSQL servers remain available for dump.
systemctl stop "tibillet-gala-backup@${GALA_SLUG}.timer"
systemctl stop "tibillet-gala-backup@${GALA_SLUG}.service"
docker stop lespass_celery lespass_django laboutik_django fedow_django >/dev/null
/usr/local/lib/tibillet-gala/backup-postgres.sh "$CONFIG"
BACKUP_ID=$(cat "$RUNTIME/last-successful-backup")
[[ "$BACKUP_ID" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || exit 1
/usr/local/lib/tibillet-gala/verify-backup-restore.sh "$CONFIG" "$BACKUP_ID"

work=$(mktemp -d "$RUNTIME/archive-config.XXXXXX")
trap 'rm -rf -- "$work"' EXIT
# Actual container environments retain the old Fernet/RSA-related settings
# even if legacy runtime files differ. This private payload never enters logs.
docker inspect fedow_django lespass_django laboutik_django \
  fedow_postgres lespass_postgres laboutik_postgres lespass_redis laboutik_redis \
  > "$work/containers.json"
git -C "$REPO_ROOT" diff --binary > "$work/generated-static.diff"
for service in lespass_redis laboutik_redis; do
  docker exec "$service" redis-cli SAVE >/dev/null
  docker cp "$service:/data" "$work/$service" >/dev/null
done
tar -C / --exclude="var/lib/tibillet-gala/gala-am-aix/${work##*/}" \
  -czf "$work/legacy-runtime.tar.gz" etc/tibillet-gala/gala-am-aix.conf \
  var/lib/tibillet-gala/gala-am-aix
tar -C "$work" -czf "$work/private-configuration.tar.gz" containers.json legacy-runtime.tar.gz \
  generated-static.diff lespass_redis laboutik_redis
(cd "$work" && sha256sum private-configuration.tar.gz > private-configuration.sha256)
prefix="s3://${BACKUP_BUCKET}/galas/${GALA_SLUG}/postgres/${BACKUP_ID}"
aws s3 cp --only-show-errors --sse AES256 "$work/private-configuration.tar.gz" "$prefix/private-configuration.tar.gz"
aws s3 cp --only-show-errors --sse AES256 "$work/private-configuration.sha256" "$prefix/private-configuration.sha256"
aws s3 cp --only-show-errors "$prefix/private-configuration.tar.gz" "$work/readback.tar.gz"
cmp -s "$work/private-configuration.tar.gz" "$work/readback.tar.gz"

# Only after the verified dump and private configuration upload do we retire
# the old servers and move their complete bind directories aside on this disk.
systemctl stop "tibillet-gala-stacks@${GALA_SLUG}.service"
docker stop fedow_postgres lespass_postgres laboutik_postgres >/dev/null
# Empty queues/caches must accompany the empty databases. Removing these
# containers without -v preserves their former anonymous Redis volumes; their
# RDB snapshots and volume references are also in the private archive above.
docker stop lespass_redis laboutik_redis fedow_memcached lespass_memcached laboutik_memcached >/dev/null
docker rm lespass_redis laboutik_redis fedow_memcached lespass_memcached laboutik_memcached >/dev/null
archive="$RUNTIME/legacy-databases/$BACKUP_ID"
mkdir -p "$archive"
for service in Fedow Lespass Laboutik; do
  mv "$REPO_ROOT/deploy/$service/database" "$archive/$service"
done

# Use the exact tested runtime. Native install commands will create and pair
# all new databases during the subsequent reviewed Production release.
git -C "$REPO_ROOT" fetch origin "$APP_COMMIT" >/dev/null 2>&1
git -C "$REPO_ROOT" restore --worktree -- deploy/Lespass/www/static/reunion/css/tibillet.css \
  deploy/Lespass/www/static/reunion/js/membership-form.mjs
git -C "$REPO_ROOT" checkout --detach "$APP_COMMIT" >/dev/null 2>&1
bash "$REPO_ROOT/deploy/tools/runtime/install-runtime-contract.sh" "$CONFIG"
python3 "$REPO_ROOT/deploy/tools/runtime/fedow-sqlite.py" prepare-empty "$REPO_ROOT" "$RUNTIME"
python3 - "$RUNTIME" "$BACKUP_ID" "$APP_COMMIT" <<'PY'
import json,sys
from pathlib import Path
root,backup,commit=Path(sys.argv[1]),sys.argv[2],sys.argv[3]
record={'gala':'gala-am-aix','legacy_backup':backup,'legacy_directory':str(root/'legacy-databases'/backup),'runtime_commit':commit,'databases_archived':3,'private_configuration_readback_verified':True}
path=root/'native-rebuild-prepared.json'
with path.open('x') as f:json.dump(record,f)
print(json.dumps(record))
PY
