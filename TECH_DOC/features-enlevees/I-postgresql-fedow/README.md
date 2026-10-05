# Configuration PostgreSQL de Fedow et retour prévu à SQLite

Le 5 octobre 2026, l'utilisateur choisit de revenir à SQLite pour Fedow et
demande de conserver la configuration PostgreSQL et le code associé pour une
éventuelle réutilisation. Ce dossier archive les sources exactes et prépare la
bascule. PostgreSQL reste configuré dans le dépôt actif à ce stade ; aucun
transfert de données, changement de serveur ou déploiement n'a été effectué.
Lespass et LaBoutik utilisent PostgreSQL dans leurs références natives et ne
sont pas concernés par ce retour.

## Sources conservées à l'identique

L'[archive de référence](reference-4c6091eb.tar.gz) contient 17 fichiers extraits
de `Rezal-KIN/Tibillet@4c6091ebf6935b5e68bd9b37fccfa54d99c1169f`, sans
réécriture. Son `manifest.json` donne, pour chaque fichier, son chemin, son blob
Git et son SHA-256. Elle conserve uniquement le code versionné : aucun fichier
`.env` réel, aucune valeur de secret runtime et aucune base de données.

SHA-256 de l'archive :
`b2183af42d3d7986933ac3786e751e4f647e2d13b9cb25da891597ada42aeb6f`.

| Sources conservées | Fonction |
| --- | --- |
| `deploy/Fedow/settings.py` | Backend PostgreSQL, noms des variables de connexion, réglages Django associés |
| `deploy/Fedow/docker-compose.yml` et `docker-compose.release.yml` | Service `fedow_postgres`, image historique, réseau, persistance et image Fedow de release |
| `deploy/tools/runtime/reconcile-fedow-webhook.py` | Agrandissement des champs chiffrés et enregistrement des clés Stripe |
| `deploy/tools/runtime/materialize-runtime-env.py` et `deploy/tools/initialize-gala-credentials.py` | Création des identifiants et production des environnements applicatifs |
| `deploy/tools/runtime/deploy-release.sh`, `preflight.sh`, `install-runtime-contract.sh` | Ordre d'initialisation, contrôles de sauvegarde et installation des scripts |
| `deploy/tools/runtime/backup-postgres.sh`, `restore-postgres.sh`, `verify-backup-restore.sh` | Dumps, restauration dédiée et contrôle isolé |
| `deploy/tools/runtime/examples/gala.conf.example` et `deploy/infra/terraform/modules/gala/bootstrap-runtime.sh.tftpl` | Liste des trois conteneurs PostgreSQL et configuration initiale de l'hôte |
| `deploy/systemd/tibillet-gala-backup.service` et `.timer` | Déclenchement des sauvegardes périodiques |
| `deploy/source/image-sources.json` | Références fixes des sources Fedow et LaBoutik |

La connexion Fedow actuelle utilise `django.db.backends.postgresql` et les
variables `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`
(défaut `postgres`) et `POSTGRES_PORT` (défaut `5432`). Le conteneur historique
emploie `postgres:13-bookworm` et monte `deploy/Fedow/database` sur
`/var/lib/postgresql/data`. Cette version est archivée comme preuve historique,
pas recommandée pour une future remise en service.

Le correctif de stockage Stripe interroge `information_schema.columns`, puis
convertit `Configuration.stripe_api_key` et `stripe_endpoint_secret_enc` en
`text` avec `ALTER TABLE`. Le modèle natif les limite à 100 caractères, alors
que le chiffrement peut dépasser cette longueur. Les commits associés sont
`45987d00` pour l'élargissement et `f2f2e8b4` pour la réconciliation de la clé API.
Ce SQL dépend de PostgreSQL et modifie le schéma en dehors des migrations Django.

L'archive reste une référence inactive. Pour récupérer un fichier sans appliquer
automatiquement les anciens réglages, l'extraire dans un répertoire de travail
séparé et comparer sa version à l'image TiBillet alors retenue. Git permet aussi
de récupérer exactement un fichier depuis le commit ci-dessus avec `git show`.
Les sauvegardes de données demeurent un sujet distinct de cette archive de code.

## Implémentation proposée pour SQLite

1. Copier textuellement le bloc `DATABASES` de
   `TiBillet/Fedow@1668d94fb2391cd1b9fef28abf857c356e13207c` :
   `django.db.backends.sqlite3`, fichier `BASE_DIR / 'database/db.sqlite3'`.
   Le diff préparé ne change que ce bloc ; il n'ajoute aucun moteur métier.
2. Donner à ce fichier un stockage persistant distinct, proposé sous
   `deploy/Fedow/sqlite-database`, monté à l'emplacement natif dans le conteneur.
   Le répertoire PostgreSQL existant est préservé. Un déploiement ordinaire ne
   doit jamais initialiser une base SQLite vide à la place d'une base existante.
3. Retirer le service PostgreSQL de la stack Fedow après qualification du
   transfert. Conserver la réconciliation des secrets Stripe, en retirant son
   élargissement SQL propre à PostgreSQL. Les setters natifs restent utilisés.
4. Adapter les sauvegardes et leur vérification : deux dumps PostgreSQL pour
   Lespass/LaBoutik et une sauvegarde cohérente SQLite pour Fedow. Une copie
   brute du seul fichier principal pendant des écritures en mode WAL ne suffit
   pas ; utiliser l'API de sauvegarde SQLite. Garder l'upload et les checksums
   existants, sans créer un second système de sauvegarde.
5. Tester le transfert sur une copie isolée avant la bascule. Préserver comptes,
   cartes, wallets, actifs, tokens, transactions, UUID, relations, clés et champs
   chiffrés. Comparer les lignes, les soldes par wallet/actif et les liens de
   transactions. Lors de la bascule, suspendre les écritures, refaire le transfert
   depuis l'état final et valider avant de rouvrir les écritures.

L'import demande une attention concrète : les signaux natifs
`first_block_for_new_asset` et `transaction_webhook_new_membership` ne filtrent
pas `raw=True`. Un `loaddata` sans précaution peut donc créer des tokens et des
transactions FIRST supplémentaires ou déclencher des appels à Lespass. La
méthode de transfert n'est pas encore qualifiée ; il faut reproduire l'import
sur une copie et éviter ces effets durant l'import, sans modifier les signaux
dans le code Fedow en service.

Une restauration PostgreSQL après de nouvelles écritures SQLite demande aussi
de transférer ces écritures : repointer simplement vers l'ancienne base ferait
perdre l'état récent. Aucune bascule automatique entre moteurs n'est proposée.

## Vérification locale de la cible native

Les 85 fichiers Python extraits ont été comparés octet par octet à l'archive
Fedow dont le checksum correspond au catalogue. Le code applicatif natif n'a
pas été modifié. Le probe PostgreSQL conservé dans l'audit initial a été adapté
uniquement dans son harness pour employer une base SQLite locale en mode WAL,
la variante native et des secrets fictifs. Les connexions réseau externes sont
interdites dans ce probe.

Les [résultats SQLite](sqlite-verification-results.json) contiennent dix
scénarios dont les résultats attendus ont été contrôlés : recharge locale,
annulation et reprise après échec local/Stripe, doublon simultané d'un checkout,
entrelacement de recharges, validation d'actif archivé, retrait de liaison à un
lieu, checkout historique nul, factures sans identifiant de session et stockage
des deux secrets chiffrés. Un seul crédit est créé lors du doublon simultané.
Les secrets fictifs de 140 et 164 caractères sont stockés et déchiffrés correctement.

Ces essais valident des chemins natifs sur une base créée pour le test. Ils ne
valident pas le transfert PostgreSQL vers SQLite, la charge du gala, un paiement
externe ou le parcours complet avec Lespass et LaBoutik. La configuration
SQLite est préparée dans `.context/sqlite-return-preview/settings.patch` et
reste distincte de la configuration active jusqu'à qualification de la bascule.
