# Runbook — sauvegardes et restauration des bases

Chaque gala a ses propres sauvegardes, chiffrées (SSE-S3), sous
`s3://<BACKUP_BUCKET>/galas/<slug>/postgres/<backup_id>/`. Aucune sauvegarde n'est partagée
entre galas — `BACKUP_BUCKET` et le préfixe viennent de la config privée de chaque instance
(`tools/runtime/examples/gala.conf.example`).

## Backup automatique

Le premier déploiement sain crée immédiatement un backup des trois bases
(deux dumps PostgreSQL pour Lespass/LaBoutik et une copie SQLite pour Fedow),
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

1. `pg_dump --format=plain --no-owner --no-privileges` sur les conteneurs
   Lespass/LaBoutik listés dans `POSTGRES_CONTAINERS`, compressé (`gzip -9`).
   La présence du montage SQLite dans le conteneur Fedow existant détermine son
   moteur : avant la bascule, le script sauvegarde encore `fedow_postgres`.
   Une ancienne config avec trois noms reste donc utilisable.
2. Pour Fedow SQLite, utilise `sqlite3.Connection.backup()` sur le fichier ouvert
   en lecture seule, puis vérifie l'intégrité, les clés étrangères et la présence
   des tables/configuration natives avant compression dans `fedow.sqlite3.gz`.
   Une copie brute du seul `db.sqlite3` pourrait oublier les écritures du WAL.
3. Écrit `metadata.txt` (gala, backup_id, platform, date, moteur Fedow, conteneurs et
   images PostgreSQL) et `SHA256SUMS` couvrant tous les dumps et métadonnées.
4. `aws s3 cp --recursive` vers le préfixe du backup, avec des chemins relatifs
   dans `SHA256SUMS` pour permettre la vérification après téléchargement. Le SQL, les identifiants et le
   contenu des secrets ne passent jamais dans les logs.
5. Écrit `$(runtime_dir)/last-successful-backup` — c'est ce fichier que
   `tools/runtime/preflight.sh` vérifie avant tout déploiement (refuse si absent, invalide,
   ou plus vieux que `MAX_BACKUP_AGE_SECONDS`).

## Backup manuel (avant une opération risquée)

```bash
sudo /usr/local/lib/tibillet-gala/backup-postgres.sh /etc/tibillet-gala/<slug>.conf
```

## Restauration PostgreSQL sur une cible dédiée

`restore-postgres.sh` reste limité aux dumps PostgreSQL. La cible doit être un
conteneur dédié sur un hôte de restauration isolé, avec le même nom que le fichier
du dump : par exemple `lespass_postgres` pour `lespass_postgres.sql.gz`. Le script
ne change pas ce nom et ne protège pas à lui seul contre le choix d’une cible live.
Il est délibérément difficile à invoquer :

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
  <target_container sur hôte isolé, ex: lespass_postgres> \
  --confirm-restore
# 3. Remettre ALLOW_RESTORE=false immédiatement après.
```

## Vérification périodique (Phase 0, bloquante avant toute migration)

`verify-backup-restore.sh` télécharge un backup, vérifie ses métadonnées et ses checksums,
puis restaure les dumps PostgreSQL présents dans cette sauvegarde, indépendamment
de la liste actuelle `POSTGRES_CONTAINERS`, dans des conteneurs jetables.
L'image est enregistrée dans les nouveaux backups. Pour les anciens dumps des
trois stacks connues, les versions historiques sont utilisées même si le
conteneur source n'existe plus.

Chaque conteneur n'a ni réseau, ni port publié, ni volume hôte ; sa mémoire est
limitée à 512 Mio et ses données temporaires disparaissent après le contrôle.
Il ne touche jamais aux bases live. Pour SQLite, le script décompresse le
snapshot dans le répertoire temporaire isolé et applique les contrôles
d'intégrité, de clés étrangères et de configuration Fedow, sans ouvrir le
stockage applicatif. Le snapshot comme les conteneurs de test disparaissent
après le contrôle. Utiliser la portée SSM approuvée pour le gala ciblé :

```bash
sudo /usr/local/lib/tibillet-gala/verify-backup-restore.sh \
  /etc/tibillet-gala/gala-am-aix.conf 20260926T121509Z
```

Consigner l'ID du backup, la validation des checksums et les résultats PostgreSQL/SQLite
(ou les trois PostgreSQL pour une ancienne sauvegarde).
Un backup qui n'a jamais été restauré avec succès n'est pas un backup vérifié. Ce drill
SQL ne remplace pas un essai applicatif complet sur une preview isolée avant une migration.

## Restauration SQLite dans un fichier isolé

Après téléchargement du backup et vérification de `SHA256SUMS`, décompresser
`fedow.sqlite3.gz` vers un **nouveau fichier** hors des données live, puis lancer :

```bash
python3 /usr/local/lib/tibillet-gala/fedow-sqlite.py verify /chemin/isole/fedow-restored.sqlite3
```

Le script vérifie uniquement ; il ne remplace pas la base active. La remise en
service d'une sauvegarde nécessite l'arrêt des écritures et une décision
opérationnelle séparée. Voir le [dossier du retour SQLite](../../../TECH_DOC/features-enlevees/I-postgresql-fedow/README.md)
pour le choix actuel de démarrage vide, la conservation de PostgreSQL et les
identifiants partagés entre les trois services.

## Ce que ce runbook ne couvre pas

- Restauration en incident sur l'instance de production live : le déblocage et la
  promotion/rollback d'une release sont couverts par `docs/operations/incident.md`, mais la
  restauration de données en place reste volontairement hors automatisation. Elle exige une
  décision explicite d'un administrateur et une cible de restauration dédiée.
- Rétention et purge (`backup_retention_days`, `aws_s3_bucket_lifecycle_configuration` dans
  `infra/terraform/storage.tf`) — automatique côté S3, aucune action manuelle requise.
