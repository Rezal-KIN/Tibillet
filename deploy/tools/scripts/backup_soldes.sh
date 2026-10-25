#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/home/ubuntu/backups"
mkdir -p $BACKUP_DIR

echo "[$DATE] Export des soldes cartes..."

# Export soldes depuis LaBoutik
docker exec laboutik_django bash -c "cd /DjangoFiles && poetry run python manage.py shell -c \"
from APIcashless.models import CarteCashless
import json
soldes = []
for c in CarteCashless.objects.all():
    assets = c.assets.filter(qty__gt=0)
    if assets.exists():
        for a in assets:
            soldes.append({
                'tag': c.tag_id,
                'asset': a.monnaie.name,
                'currency_code': a.monnaie.currency_code,
                'solde': str(a.qty)
            })
print(json.dumps(soldes, indent=2))
\"" > $BACKUP_DIR/soldes_$DATE.json

echo "[$DATE] Fichier créé : soldes_$DATE.json"
cat $BACKUP_DIR/soldes_$DATE.json

# Upload vers Google Drive
rclone copy $BACKUP_DIR/soldes_$DATE.json "gdrive:PP BDD backup/"
echo "[$DATE] Upload Google Drive OK ✅"

# Garder seulement les 50 derniers fichiers locaux
ls -t $BACKUP_DIR/soldes_*.json | tail -n +51 | xargs -r rm
