# Périmètre runtime et portes de changement

## Cible autorisée

Tout nouvel outil AWS ou runtime de ce dépôt doit cibler exclusivement une instance Gala neuve
créée à Paris. `TibilletBapts` est arrêtée et conservée uniquement comme archive de secours ; elle
ne doit jamais devenir une cible de déploiement, d'import Terraform ou de redémarrage automatique.

| Champ | Valeur |
| --- | --- |
| Compte AWS | `318629836660` |
| Région runtime | `eu-west-3` |
| Instance | une EC2 Gala créée par Terraform, puis inscrite avec son ID réel dans `ops/policy/runtime-allowlist.yaml` |
| Tag `Name` attendu | `tibillet-gala-<slug>` |

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

Exemple de validation après création d'une instance Paris et mise à jour explicite de
l'allowlist avec son identité réelle :

```bash
python3 tools/validate-runtime-scope.py \
  --account 318629836660 \
  --region eu-west-3 \
  --instance i-REPLACE_WITH_TERRAFORM_OUTPUT \
  --instance-name tibillet-gala-REPLACE_WITH_SLUG
```

Une référence explicitement refusée doit être transmise avec `--reference`; le validateur échoue alors avant toute commande opérationnelle.

## Portes de changement

| Porte | Autorisé | Interdit |
| --- | --- | --- |
| Inventaire | AWS/SSH lecture seule sur l'instance Paris approuvée | lecture de secrets, `.env`, contenu de backup, mutation AWS/Docker/systemd |
| Plan Terraform | `fmt`, `init -backend=false`, `validate`, plan revu | `apply`, import Bapts, création de ressource additive |
| Fondations additives | uniquement après plan approuvé et approbation CodeBuild | création EC2 hors `eu-west-3`, secrets dans les variables CodeBuild, cible non allowlistée |
| Promotion production | après bootstrap, backup et restauration isolée validés | `latest`, déploiement sans approbation, stack legacy/V2 preview |

Les domaines et capacité sont des paramètres non secrets validés du workflow CodeBuild de
fondation. Les DNS, certificats, preview publique et qualification V2 restent des portes séparées
avant toute bascule publique.
