#!/usr/bin/env bash
set -euo pipefail

DATE=$(date +%Y%m%d_%H%M%S)
RESET_SCOPE="${RESET_SCOPE:-ALL}"  # ALL ou nom d'asset (ex: KIN_COIN)
SKIP_BACKUP="${SKIP_BACKUP:-0}"    # 1 pour sauter l'export backup

log() {
  echo "[$DATE] $*"
}

echo "=============================="
echo "  RESET SOLDES TIBILLET"
echo "=============================="
log "Mode reset: ${RESET_SCOPE}"

# 1. BACKUP avant tout
if [ "${SKIP_BACKUP}" = "1" ]; then
  log "1. Backup saute (SKIP_BACKUP=1)."
elif [ -f /home/ubuntu/backup_soldes.sh ]; then
  log "1. Backup des soldes avant reset..."
  /home/ubuntu/backup_soldes.sh
else
  log "1. Pas de script backup trouvé, on continue..."
fi

# 2. Récupération du domaine Fedow depuis la config Django
log "2. Vérification de la configuration Fedow..."
FEDOW_DOMAIN=$(docker exec laboutik_django bash -lc "cd /DjangoFiles && poetry run python manage.py shell -c \"from APIcashless.models import Configuration; print(Configuration.get_solo().fedow_domain, end='')\"")

if [ -z "${FEDOW_DOMAIN}" ]; then
  log "ERREUR: domaine Fedow vide dans la configuration."
  exit 1
fi

log "Fedow configuré: ${FEDOW_DOMAIN}"

# 3. Test connectivité HTTPS avant de lancer les refunds
log "3. Vérification accessibilité HTTPS Fedow..."
if ! docker exec laboutik_django bash -lc "timeout 8 bash -lc 'echo | openssl s_client -connect ${FEDOW_DOMAIN}:443 -servername ${FEDOW_DOMAIN} >/dev/null 2>&1'"; then
  log "Fedow inaccessible via IP publique, tentative de routage local via Traefik..."

  # S'assure que laboutik_django peut atteindre traefik sur le réseau frontend
  docker network connect frontend laboutik_django >/dev/null 2>&1 || true
  TRAEFIK_IP=$(docker inspect --format '{{range $k,$v := .NetworkSettings.Networks}}{{if eq $k "frontend"}}{{$v.IPAddress}}{{end}}{{end}}' traefik)

  if [ -z "${TRAEFIK_IP}" ]; then
    log "ERREUR: impossible de déterminer l'IP Traefik sur le réseau frontend."
    exit 1
  fi

  # Force la résolution du domaine Fedow vers Traefik local (évite le hairpin NAT)
  docker exec -u 0 laboutik_django bash -lc "grep -v '${FEDOW_DOMAIN}' /etc/hosts > /tmp/hosts.new && echo '${TRAEFIK_IP} ${FEDOW_DOMAIN}' >> /tmp/hosts.new && cat /tmp/hosts.new > /etc/hosts"

  if ! docker exec laboutik_django bash -lc "timeout 8 bash -lc 'echo | openssl s_client -connect ${FEDOW_DOMAIN}:443 -servername ${FEDOW_DOMAIN} >/dev/null 2>&1'"; then
    log "ERREUR: Fedow injoignable sur ${FEDOW_DOMAIN}:443 même après routage local. Reset annulé."
    exit 1
  fi

  log "Routage local Fedow activé via Traefik (${TRAEFIK_IP})."
fi

# 4. Refund via Fedow
log "4. Remise à zéro des soldes via Fedow..."
if ! docker exec -e RESET_SCOPE="${RESET_SCOPE}" laboutik_django bash -lc "cd /DjangoFiles && poetry run python manage.py shell -c \"
import os
from APIcashless.models import CarteCashless, Configuration, CarteMaitresse
from fedow_connect.fedow_api import _post

reset_scope = os.getenv('RESET_SCOPE', 'ALL').strip().upper()
carte_maitresse = CarteMaitresse.objects.first()
if not carte_maitresse:
    print('ERREUR: Aucune carte maîtresse trouvée.')
    raise SystemExit(1)

primary_tag = carte_maitresse.carte.tag_id
config = Configuration.get_solo()

if reset_scope == 'ALL':
    cartes_qs = CarteCashless.objects.filter(assets__qty__gt=0).distinct()
else:
    cartes_qs = CarteCashless.objects.filter(
        assets__qty__gt=0,
        assets__monnaie__name=reset_scope,
    ).distinct()

print('Carte maîtresse détectée:', primary_tag)
print('Instance:', config.fedow_domain)
print('Scope reset:', reset_scope)
print()

cartes_avec_solde = 0
refund_ok = 0
refund_ko = 0
local_assets_zeroed = 0

for c in cartes_qs.iterator():
    cartes_avec_solde += 1
    refund_data = {
        'user_card_firstTagId': c.tag_id,
        # Orthographe historique attendue par l'API Fedow actuelle
        'primary_card_fisrtTagId': primary_tag,
        'action': 'RFD',
    }

    try:
        response = _post(config, 'card/refund', refund_data)
    except Exception as exc:
        refund_ko += 1
        print('ERREUR RESEAU', c.tag_id, ':', str(exc)[:300])
        continue

    if response.status_code == 205:
        refund_ok += 1
        if reset_scope == 'ALL':
            local_assets_zeroed += c.assets.filter(qty__gt=0).update(qty=0)
        else:
            local_assets_zeroed += c.assets.filter(
                qty__gt=0,
                monnaie__name=reset_scope,
            ).update(qty=0)
        print('REFUND OK:', c.tag_id)
    else:
        refund_ko += 1
        body = response.content.decode('utf-8', errors='ignore')[:300]
        print('ERREUR API', c.tag_id, ':', response.status_code, body)

if cartes_avec_solde == 0:
    print('Aucune carte avec solde trouvee pour ce scope.')
else:
    print()
    print('Cartes avec solde trouvees :', cartes_avec_solde)
    print('Refund OK :', refund_ok)
    print('Refund ERREUR :', refund_ko)
    print('Assets locaux remis a 0 :', local_assets_zeroed)

if refund_ko > 0:
    raise SystemExit(2)
\""; then
  log "ERREUR: la phase refund a échoué. Reset interrompu."
  exit 1
fi

# 5. Vidage cache Redis
log "5. Vidage cache Redis..."
docker exec laboutik_redis redis-cli FLUSHALL >/dev/null
log "Cache Redis vide."

# 6. Marqueur de nouvelle session pour dashboard Fedow /suivi
SUIVI_MARKER_FILE="/home/ubuntu/TiBillet/Fedow/www/suivi_session_start.txt"
SUIVI_BASELINE_FILE="/home/ubuntu/TiBillet/Fedow/www/suivi_wallet_baseline_cents.txt"
mkdir -p "$(dirname "${SUIVI_MARKER_FILE}")"
date --iso-8601=seconds > "${SUIVI_MARKER_FILE}"
WALLET_BASELINE_CENTS=$(docker exec fedow_django bash -lc "cd /home/fedow/Fedow && poetry run python manage.py shell -c \"
from django.db.models import Sum
from fedow_core.models import Token, Asset
total = Token.objects.filter(
    wallet__place__isnull=True,
    asset__category__in=[Asset.STRIPE_FED_FIAT, Asset.TOKEN_LOCAL_FIAT, Asset.TOKEN_LOCAL_NOT_FIAT],
).aggregate(total=Sum('value'))['total'] or 0
print(int(total), end='')
\"")
echo "${WALLET_BASELINE_CENTS}" > "${SUIVI_BASELINE_FILE}"
log "6. Session suivi réinitialisée (${SUIVI_MARKER_FILE}) avec baseline wallet=${WALLET_BASELINE_CENTS} cents (${SUIVI_BASELINE_FILE})."

echo "=============================="
echo "  RESET SOLDES TERMINE"
echo "=============================="
