#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  create_laboutik_instance.sh --gala-id "BAPTS_225" [--domain "bapts-225.cashless.galas-am-aix.rezal.fr"] [--dry-run]

Description:
  Create a fresh LaBoutik instance folder + containers for one gala.
  It reuses the current LaBoutik code/config template and starts a dedicated docker-compose project.
EOF
}

GALA_ID=""
DOMAIN=""
DRY_RUN=0
ADMIN_USERNAME="${LABOUTIK_ADMIN_USERNAME:-admin}"
ADMIN_PASSWORD="${LABOUTIK_ADMIN_PASSWORD:-rezalnorms}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --gala-id)
      GALA_ID="${2:-}"
      shift 2
      ;;
    --domain)
      DOMAIN="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$GALA_ID" ]]; then
  echo "Missing --gala-id" >&2
  usage
  exit 1
fi

TEMPLATE_DIR="/home/ubuntu/TiBillet/Laboutik"
if [[ ! -d "$TEMPLATE_DIR" ]]; then
  echo "Template dir not found: $TEMPLATE_DIR" >&2
  exit 1
fi

slug="$(echo "$GALA_ID" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')"
if [[ -z "$slug" ]]; then
  echo "Invalid gala id: $GALA_ID" >&2
  exit 1
fi

if [[ -z "$DOMAIN" ]]; then
  DOMAIN="${slug}.cashless.galas-am-aix.rezal.fr"
fi

INSTANCE_DIR="/home/ubuntu/TiBillet/Laboutik_${slug}"
PROJECT_NAME="laboutik_${slug}"
ROUTER_NAME="laboutik_${slug}"
ASSET_NAME="${GALA_ID} COIN"

if [[ -e "$INSTANCE_DIR" ]]; then
  existing_count="$(docker ps -a --filter "label=com.docker.compose.project=${PROJECT_NAME}" -q | wc -l | tr -d ' ')"
  if [[ "${existing_count}" != "0" ]]; then
    echo "Instance already provisioned: $INSTANCE_DIR (project ${PROJECT_NAME})"
    exit 0
  fi
  echo "Instance dir already exists but no compose project found: $INSTANCE_DIR" >&2
  echo "Manual cleanup required before retry." >&2
  exit 1
fi

echo "Creating instance:"
echo "  gala-id: $GALA_ID"
echo "  domain:  $DOMAIN"
echo "  dir:     $INSTANCE_DIR"
echo "  project: $PROJECT_NAME"

mkdir -p "$INSTANCE_DIR"
cp -a "$TEMPLATE_DIR/docker-compose.yml" "$INSTANCE_DIR/docker-compose.yml"
cp -a "$TEMPLATE_DIR/.env" "$INSTANCE_DIR/.env"
cp -a "$TEMPLATE_DIR/settings.py" "$INSTANCE_DIR/settings.py"
cp -a "$TEMPLATE_DIR/views.py" "$INSTANCE_DIR/views.py"
cp -a "$TEMPLATE_DIR/validators.py" "$INSTANCE_DIR/validators.py"
cp -a "$TEMPLATE_DIR/fedow_api.py" "$INSTANCE_DIR/fedow_api.py"
cp -a "$TEMPLATE_DIR/nginx" "$INSTANCE_DIR/nginx"
cp -a "$TEMPLATE_DIR/ssh" "$INSTANCE_DIR/ssh"

mkdir -p "$INSTANCE_DIR/backup" "$INSTANCE_DIR/logs" "$INSTANCE_DIR/www" "$INSTANCE_DIR/database/data"

upsert_env() {
  local file="$1" key="$2" value="$3"
  if grep -qE "^${key}=" "$file"; then
    sed -i "s|^${key}=.*|${key}=${value}|g" "$file"
  else
    printf "\n%s=%s\n" "$key" "$value" >> "$file"
  fi
}

upsert_env "$INSTANCE_DIR/.env" "DOMAIN" "$DOMAIN"
upsert_env "$INSTANCE_DIR/.env" "MAIN_ASSET_NAME" "$ASSET_NAME"
upsert_env "$INSTANCE_DIR/.env" "ENABLE_GIFT_ASSET_SYNC" "0"
upsert_env "$INSTANCE_DIR/.env" "GALA_ID" "$GALA_ID"
upsert_env "$INSTANCE_DIR/.env" "ROUTER_NAME" "$ROUTER_NAME"

if [[ -f "$INSTANCE_DIR/nginx/laboutique.conf" ]]; then
  sed -i "s|server_name .*;|server_name ${DOMAIN};|g" "$INSTANCE_DIR/nginx/laboutique.conf"
fi

sed -i '/container_name:/d;/hostname:/d' "$INSTANCE_DIR/docker-compose.yml"
sed -i "s/traefik\\.http\\.routers\\.laboutik_nginx/traefik.http.routers.${ROUTER_NAME}/g" "$INSTANCE_DIR/docker-compose.yml"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Dry-run done. No containers started."
  echo "To start:"
  echo "  cd $INSTANCE_DIR && docker compose --project-name $PROJECT_NAME up -d"
  exit 0
fi

cd "$INSTANCE_DIR"
docker compose --project-name "$PROJECT_NAME" up -d

echo "Ensuring Django admin user exists: ${ADMIN_USERNAME}"
admin_bootstrap_ok=0
for attempt in $(seq 1 30); do
  if docker compose --project-name "$PROJECT_NAME" exec -T laboutik_django poetry run python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
u, created = User.objects.get_or_create(username='${ADMIN_USERNAME}')
u.is_staff = True
u.is_superuser = True
u.is_active = True
u.set_password('${ADMIN_PASSWORD}')
u.save()
print('admin_user', 'created' if created else 'updated')
" >/tmp/laboutik_admin_bootstrap.log 2>&1; then
    admin_bootstrap_ok=1
    cat /tmp/laboutik_admin_bootstrap.log
    break
  fi
  sleep 3
done

if [[ "$admin_bootstrap_ok" -ne 1 ]]; then
  echo "WARNING: admin bootstrap failed after retries." >&2
  echo "Check container logs and run the bootstrap manually." >&2
fi

echo
echo "Instance started."
echo "Add DNS A record:"
echo "  *.cashless.galas-am-aix.rezal.fr -> 13.61.201.166"
echo "  or set ${DOMAIN} if you prefer a dedicated record"
echo
echo "Check:"
echo "  docker compose --project-name $PROJECT_NAME ps"
