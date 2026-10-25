# Runbook — sauvegardes et restauration des bases

Chaque gala a ses propres sauvegardes, chiffrées (SSE-S3), sous
`s3://<BACKUP_BUCKET>/galas/<slug>/postgres/<backup_id>/`. Aucune sauvegarde n'est partagée
entre galas — `BACKUP_BUCKET` et le préfixe viennent de la config privée de chaque instance
(`tools/runtime/examples/gala.conf.example`).

## Accord ponctuel obligatoire

Chaque nouvelle sauvegarde de données réelles exige l'accord préalable de
l'utilisateur, pour un gala, un contenu et un volume estimé. Une approbation de
déploiement ou d'arrêt d'EC2 ne vaut pas approbation de sauvegarde. Un accord ne
permet ni une récurrence ni une deuxième sauvegarde. Les tests avec données
fictives et une restauration temporaire d'un backup existant restent possibles.

Il n'y a plus de sauvegarde périodique. L'installation du runtime et chaque
déploiement désactivent et masquent les anciens minuteurs/services, y compris
sur un hôte où l'ancien modèle toutes les six heures reste installé. Un reboot
ne doit pas les réactiver. Les sauvegardes existantes sont conservées.

Le script refuse un appel sans `BACKUP_ID --confirm-backup`, ainsi que la
réutilisation d'un identifiant déjà consommé ou présent dans S3. L'opérateur ne
passe cette confirmation qu'après accord de l'utilisateur. Un appel échoué ou
une réponse perdue nécessite l'inspection du même identifiant et de son reçu
local (`backup-requests/<backup_id>/status`), jamais une nouvelle sauvegarde
automatique.

Un déploiement ne crée aucun backup implicitement. Il est bloqué si le backup
préalable est absent ou trop ancien. Le premier déploiement sur base vide peut
démarrer les services, mais sa finalisation attend une sauvegarde approuvée ;
un ancien dump PostgreSQL ne peut pas valider un nouveau stockage Fedow SQLite.

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
4. `aws s3 cp --recursive` vers le préfixe du backup, puis téléchargement dans un
   répertoire temporaire et vérification des checksums. Les chemins sont relatifs
   dans `SHA256SUMS` pour permettre la vérification après téléchargement. Le SQL, les identifiants et le
   contenu des secrets ne passent jamais dans les logs.
5. Écrit les métadonnées et `$(runtime_dir)/last-successful-backup` après vérification — c'est ce fichier que
   `tools/runtime/preflight.sh` vérifie avant tout déploiement (refuse si absent, invalide,
   ou plus vieux que `MAX_BACKUP_AGE_SECONDS`).

## Une sauvegarde après accord de l'utilisateur

Estimer d'abord le volume et vérifier les backups existants. Si un backup
existant suffit, le contrôler plutôt que créer une copie supplémentaire.
Après accord pour cette sauvegarde unique, choisir une seule fois son identifiant :

```bash
BACKUP_ID="$(date -u +%Y%m%dT%H%M%SZ)"
sudo /usr/local/lib/tibillet-gala/backup-postgres.sh \
  /etc/tibillet-gala/<slug>.conf "$BACKUP_ID" --confirm-backup
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
- Rétention et purge : la règle actuelle de `infra/terraform/storage.tf` expire
  uniquement les anciennes versions d'objets. Les backups portant chacun un nom
  daté ne sont pas supprimés automatiquement. Toute future politique doit
  distinguer les sauvegardes courantes des archives finales, sans supprimer une
  archive nécessaire à la restauration d'un gala dont les disques ont été retirés.
