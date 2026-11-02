#!/usr/bin/env bash
# Web only: the existing lespass_celery service owns the worker and beat.
set -euo pipefail
cd /DjangoFiles
mkdir -p logs/supervisor
touch logs/Djangologfile logs/gunicorn.logs logs/daphne.logs
exec /usr/bin/supervisord -c deploy/estia/gala-test/supervisord-web.conf
