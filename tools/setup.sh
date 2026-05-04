#!/usr/bin/env bash
# Setup initial d'une nouvelle VM — à lancer une seule fois depuis la racine du repo.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFISICAL_PROJECT_ID="54d21571-81e2-48ae-8853-188230ce3394"

cd "$REPO_ROOT"

echo "=== Setup TiBillet ==="
echo ""

# --- Prérequis ---
for cmd in docker infisical; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "ERREUR : '$cmd' n'est pas installé." >&2
    exit 1
  fi
done

# --- Réseau Docker frontend ---
if ! docker network inspect frontend &>/dev/null; then
  echo "[1/5] Création du réseau Docker 'frontend'..."
  docker network create frontend
else
  echo "[1/5] Réseau 'frontend' déjà présent."
fi

# --- acme.json ---
ACME="$REPO_ROOT/traefik/acme.json"
if [ ! -f "$ACME" ]; then
  echo "[2/5] Initialisation de traefik/acme.json..."
  touch "$ACME"
  chmod 600 "$ACME"
else
  echo "[2/5] traefik/acme.json déjà présent."
  # Traefik exige chmod 600 — on s'assure que c'est correct
  chmod 600 "$ACME"
fi

# --- Traefik ---
echo "[3/5] Démarrage de Traefik..."
docker compose -f "$REPO_ROOT/traefik/docker-compose.yml" up -d

# --- Credentials Infisical ---
echo "[4/5] Configuration des credentials Infisical..."
bash "$REPO_ROOT/tools/setup_infisical.sh"

# --- Export des .env depuis Infisical ---
echo "[5/5] Récupération des .env depuis Infisical..."

CREDS_FILE="$HOME/.infisical-credentials"
if [ -f "$CREDS_FILE" ]; then
  source "$CREDS_FILE"
fi

export_env() {
  local service="$1"
  local dest="$REPO_ROOT/$service/.env"
  echo "  → $service/.env"
  infisical export \
    --projectId="$INFISICAL_PROJECT_ID" \
    --env=prod \
    --token="" 2>/dev/null \
    > "$dest" \
    || infisical export \
         --projectId="$INFISICAL_PROJECT_ID" \
         --env=prod \
         > "$dest"
}

export_env Fedow
export_env Lespass
export_env Laboutik

echo ""
echo "Setup terminé. Pour démarrer les services :"
echo "  cd Fedow   && docker compose up -d && cd .."
echo "  cd Lespass && docker compose up -d && cd .."
echo "  cd Laboutik && docker compose up -d && cd .."
echo ""
echo "Les certificats TLS seront générés automatiquement par Traefik"
echo "au premier accès à chaque domaine."
