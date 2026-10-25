#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/home/ubuntu/TiBillet"

# Ensure the shared Traefik network exists before bringing up stacks that use it.
docker network inspect frontend >/dev/null 2>&1 || docker network create frontend >/dev/null

STACK_DIRS=(
  "$REPO_ROOT/traefik"
  "$REPO_ROOT/Fedow"
  "$REPO_ROOT/Lespass"
  "$REPO_ROOT/Laboutik_100-jours-225"
)

for stack_dir in "${STACK_DIRS[@]}"; do
  if [[ -f "$stack_dir/docker-compose.yml" ]]; then
    docker compose -f "$stack_dir/docker-compose.yml" up -d
  fi
done
