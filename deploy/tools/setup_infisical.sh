#!/usr/bin/env bash
set -euo pipefail

CREDS_FILE="$HOME/.infisical-credentials"

# Crée le fichier s'il n'existe pas
if [ ! -f "$CREDS_FILE" ]; then
  cat > "$CREDS_FILE" <<'EOF'
export INFISICAL_CLIENT_ID=
export INFISICAL_CLIENT_SECRET=
EOF
  chmod 600 "$CREDS_FILE"
fi

# Charge les valeurs actuelles
source "$CREDS_FILE"

echo "=== Configuration Infisical ==="
echo ""
echo "Laisse vide pour conserver la valeur actuelle."
echo ""

# Client ID
if [ -n "${INFISICAL_CLIENT_ID:-}" ]; then
  echo "Client ID actuel : ${INFISICAL_CLIENT_ID:0:8}... (masqué)"
else
  echo "Client ID actuel : (vide)"
fi
read -rp "Nouveau Client ID : " NEW_CLIENT_ID
CLIENT_ID="${NEW_CLIENT_ID:-$INFISICAL_CLIENT_ID}"

# Client Secret
if [ -n "${INFISICAL_CLIENT_SECRET:-}" ]; then
  echo "Client Secret actuel : ${INFISICAL_CLIENT_SECRET:0:8}... (masqué)"
else
  echo "Client Secret actuel : (vide)"
fi
read -rsp "Nouveau Client Secret : " NEW_CLIENT_SECRET
echo ""
CLIENT_SECRET="${NEW_CLIENT_SECRET:-$INFISICAL_CLIENT_SECRET}"

# Écrit les nouvelles valeurs
cat > "$CREDS_FILE" <<EOF
export INFISICAL_CLIENT_ID=$CLIENT_ID
export INFISICAL_CLIENT_SECRET=$CLIENT_SECRET
EOF
chmod 600 "$CREDS_FILE"

# Active dans la session courante
source "$CREDS_FILE"

echo ""
echo "Credentials sauvegardés dans $CREDS_FILE"
echo "Pour les charger dans un nouveau terminal : source $CREDS_FILE"
echo ""

# Ajoute le source au .bashrc si pas déjà présent
if ! grep -q "infisical-credentials" "$HOME/.bashrc" 2>/dev/null; then
  echo "[ -f $CREDS_FILE ] && source $CREDS_FILE" >> "$HOME/.bashrc"
  echo "Ajouté au .bashrc — chargement automatique à chaque session."
fi
