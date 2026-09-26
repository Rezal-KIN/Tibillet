# Runbook — backup et restauration PostgreSQL

Chaque gala a ses propres dumps PostgreSQL, chiffrés (SSE-S3), sous
`s3://<BACKUP_BUCKET>/galas/<slug>/postgres/<backup_id>/`. Aucune sauvegarde n'est partagée
entre galas — `BACKUP_BUCKET` et le préfixe viennent de la config privée de chaque instance
(`tools/runtime/examples/gala.conf.example`).

## Backup automatique

Le premier déploiement sain crée immédiatement un backup des trois bases,
vérifie l'upload, puis démarre `systemd/tibillet-gala-backup.timer`. Celui-ci
déclenche `tibillet-gala-backup@<slug>.service` toutes les 6 heures
(00h/06h/12h/18h15 UTC, `Persistent=true` — rattrape un backup manqué au
prochain boot si l'instance était arrêtée à l'heure prévue). Aucun déploiement
suivant ne peut utiliser `ALLOW_INITIAL_DEPLOY` pour contourner un backup
absent ou périmé.

```bash
sudo systemctl enable --now tibillet-gala-backup@gala-am-aix.timer
sudo systemctl list-timers 'tibillet-gala-backup*'
```

`backup-postgres.sh` :
1. `pg_dump --format=plain --no-owner --no-privileges` sur chaque conteneur listé dans
   `POSTGRES_CONTAINERS`, compressé (`gzip -9`).
2. Écrit `metadata.txt` (gala, backup_id, platform, date) et `SHA256SUMS` couvrant les
   dumps et les métadonnées.
3. `aws s3 cp --recursive` vers le préfixe du backup, avec des chemins relatifs
   dans `SHA256SUMS` pour permettre la vérification après téléchargement. Le SQL, les identifiants et le
   contenu des secrets ne passent jamais dans les logs.
4. Écrit `$(runtime_dir)/last-successful-backup` — c'est ce fichier que
   `tools/runtime/preflight.sh` vérifie avant tout déploiement (refuse si absent, invalide,
   ou plus vieux que `MAX_BACKUP_AGE_SECONDS`).

## Backup manuel (avant une opération risquée)

```bash
sudo /usr/local/lib/tibillet-gala/backup-postgres.sh /etc/tibillet-gala/<slug>.conf
```

## Restauration — toujours sur une cible dédiée, jamais en place

`restore-postgres.sh` est délibérément difficile à invoquer :

- `ALLOW_RESTORE=true` doit être explicitement présent dans la config root-owned (par
  défaut `false` dans `gala.conf.example`) — ce n'est pas un flag qu'on laisse activé.
- Le 4ème argument doit être littéralement `--confirm-restore`.
- Le script vérifie les checksums (`sha256sum -c`) avant toute restauration et échoue à la
  première erreur SQL (`ON_ERROR_STOP=1`). Il ne fait jamais de `DROP`/`CREATE DATABASE` —
  la cible doit déjà être une base de restauration dédiée, vide.

```bash
# 1. Activer temporairement dans /etc/tibillet-gala/<slug>.conf : ALLOW_RESTORE=true
# 2. Choisir un conteneur PostgreSQL cible qui N'EST PAS un conteneur de prod live —
#    une preview isolée (voir docs/aws-access.md pour la portée gala-elevated).
sudo /usr/local/lib/tibillet-gala/restore-postgres.sh \
  /etc/tibillet-gala/<slug>.conf \
  <backup_id ex: 20270615T061500Z> \
  <target_container ex: preview_lespass_postgres> \
  --confirm-restore
# 3. Remettre ALLOW_RESTORE=false immédiatement après.
```

## Vérification périodique (Phase 0, bloquante avant toute migration)

`verify-backup-restore.sh` télécharge un backup, vérifie ses métadonnées et ses checksums,
puis restaure chaque dump dans un conteneur PostgreSQL jetable du même type que la source.
Ce conteneur n'a ni réseau, ni port publié, ni volume hôte ; sa mémoire est limitée à
512 Mio et ses données temporaires disparaissent après le contrôle. Il ne touche jamais
aux bases live. Utiliser la portée SSM approuvée pour le gala ciblé :

```bash
sudo /usr/local/lib/tibillet-gala/verify-backup-restore.sh \
  /etc/tibillet-gala/gala-am-aix.conf 20260926T121509Z
```

Consigner l'ID du backup, la validation des checksums et les trois résultats de restauration.
Un backup qui n'a jamais été restauré avec succès n'est pas un backup vérifié. Ce drill
SQL ne remplace pas un essai applicatif complet sur une preview isolée avant une migration.

## Ce que ce runbook ne couvre pas

- Restauration en incident sur l'instance de production live : le déblocage et la
  promotion/rollback d'une release sont couverts par `docs/operations/incident.md`, mais la
  restauration de données en place reste volontairement hors automatisation. Elle exige une
  décision explicite d'un administrateur et une cible de restauration dédiée.
- Rétention et purge (`backup_retention_days`, `aws_s3_bucket_lifecycle_configuration` dans
  `infra/terraform/storage.tf`) — automatique côté S3, aucune action manuelle requise.
