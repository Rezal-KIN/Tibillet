# Périmètre runtime et portes de changement

## Cible autorisée

Tout nouvel outil AWS ou runtime de ce dépôt doit cibler exclusivement :

| Champ | Valeur |
| --- | --- |
| Compte AWS | `318629836660` |
| Région runtime | `eu-north-1` |
| Instance | `i-0cd4e52913c8ae928` |
| Tag `Name` attendu | `TibilletBapts` |

Avant toute commande AWS, vérifier l'identité effective :

```bash
aws sts get-caller-identity --profile gala-operator
```

Le champ `Account` doit être `318629836660`. Le compte Méthodo est `051826693409` et ne doit jamais être ciblé par cet outillage.

## Cibles et chemins refusés

Les éléments suivants sont hors périmètre de toute automatisation nouvelle :

- instances `Tibillet100J_OG`, `PPSCP`, `TibilletSiteKfet` ;
- stacks `Laboutik_100-jours-225` et `Lespass-v2` ;
- `tools/start-stacks-on-boot.sh` ;
- `tools/scripts/backup_soldes.sh` et `tools/scripts/reset_soldes.sh`.

`PPSCP` reste arrêtée et préservée. `TibilletSiteKfet` a été supprimée et ne doit pas être recréée. `Tibillet100J_OG` est hors périmètre absolu.

Les sauvegardes legacy sont préservées, sans lecture de leur contenu, migration, purge, activation de timer ni consommation par une future pipeline. Leur refonte est un chantier distinct.

## Validateur obligatoire

`tools/validate-runtime-scope.py` lit les politiques versionnées :

- `ops/policy/runtime-allowlist.yaml`
- `ops/policy/denied-targets.yaml`

Exemple de validation avant un inventaire Bapts :

```bash
python3 tools/validate-runtime-scope.py \
  --account 318629836660 \
  --region eu-north-1 \
  --instance i-0cd4e52913c8ae928 \
  --instance-name TibilletBapts
```

Une référence explicitement refusée doit être transmise avec `--reference`; le validateur échoue alors avant toute commande opérationnelle.

## Portes de changement

| Porte | Autorisé | Interdit |
| --- | --- | --- |
| Inventaire | AWS/SSH lecture seule sur Bapts | lecture de secrets, `.env`, contenu de backup, mutation AWS/Docker/systemd |
| Plan Terraform | `fmt`, `init -backend=false`, `validate`, plan revu | `apply`, import Bapts, création de ressource additive |
| Fondations additives | uniquement après plan approuvé | SSM, instance profile, secrets runtime, backup, pipeline Production |
| Promotion production | chantier ultérieur après backups restaurés avec succès | rebuild sur Bapts, `latest`, déploiement sans approbation |

Les domaines, DNS, certificats, preview publique et qualification V2 sont reportés et ne font partie d'aucune porte actuelle.
