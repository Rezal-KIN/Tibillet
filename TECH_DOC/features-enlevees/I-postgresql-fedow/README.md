# Configuration PostgreSQL de Fedow et retour prévu à SQLite

Le 5 octobre 2026, l'utilisateur choisit de revenir à SQLite pour Fedow et
de conserver la configuration PostgreSQL pour une éventuelle réutilisation.
Il précise qu'aucune instance n'est en production et choisit explicitement une
**base SQLite vide, avec l'ancien PostgreSQL conservé à part**. Le transfert des
données est donc abandonné pour simplifier ce retour.

Le dépôt local utilise maintenant SQLite. Aucun push, déploiement, effacement de
base ou changement sur une instance distante n'a été effectué. Lespass et
LaBoutik conservent PostgreSQL, leur moteur natif dans les références retenues.

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

La connexion Fedow archivée utilisait `django.db.backends.postgresql` et les
variables `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`
(défaut `postgres`) et `POSTGRES_PORT` (défaut `5432`). Le conteneur historique
emploie `postgres:13-bookworm` et monte `deploy/Fedow/database` sur
`/var/lib/postgresql/data`. Cette version est archivée comme preuve historique,
pas recommandée pour une future remise en service.

Le correctif de stockage Stripe archivé interroge `information_schema.columns`, puis
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

## Retour local au fonctionnement natif

Le bloc `DATABASES` de `deploy/Fedow/settings.py` est copié textuellement depuis
`TiBillet/Fedow@1668d94fb2391cd1b9fef28abf857c356e13207c` :
`django.db.backends.sqlite3`, fichier `BASE_DIR / 'database/db.sqlite3'`.
Le vérificateur `../verify-restored-code.py` contrôle cette égalité exacte contre
l'archive dont le checksum est fixé dans `deploy/source/image-sources.json`.
Aucun modèle, serializer, migration ou signal Fedow n'est réécrit.

Compose retire le service `fedow_postgres` et son lien, et monte uniquement les
**données SQLite** de `deploy/Fedow/sqlite-database` à l'emplacement natif
`/home/fedow/Fedow/database`. Cette persistance est nécessaire pour conserver les
soldes lors d'un remplacement de conteneur. `deploy/Fedow/database`, l'ancien
répertoire PostgreSQL, n'est ni effacé, ni réutilisé, ni changé de propriétaire.
L'entrée native `start.sh` continue d'appliquer les migrations, l'installation et
le mode WAL. Les autres personnalisations conservées ne changent pas ici.

La réconciliation Stripe conserve les setters et accesseurs natifs et retire
l'agrandissement SQL des champs propre à PostgreSQL. SQLite accepte les textes
chiffrés de 140 et 164 caractères dans les champs natifs. Le schéma des secrets
runtime reste compatible : `fedow_postgres_password` et ses variables sont
encore générés et matérialisés, mais ignorés par SQLite. Cela évite de modifier
ou renouveler les secrets partagés au cours de ce retour.

Les sauvegardes existantes couvrent maintenant deux dumps PostgreSQL et une
copie cohérente SQLite via `sqlite3.Connection.backup()`. Leur nom historique
`backup-postgres.sh` et leur préfixe S3 sont conservés pour les timers et les
anciens backups. Le type de sauvegarde Fedow dépend du montage du conteneur
existant ; une ancienne configuration listant trois conteneurs reste utilisable.
La vérification restaure aussi les anciennes sauvegardes Fedow PostgreSQL quand
le conteneur source a disparu. Voir le [runbook](../../../deploy/docs/operations/backup-restore.md).

## Démarrage sur une base vide

La voie la plus simple est une **instance dédiée entièrement neuve**, avec les
trois services initialisés par les commandes TiBillet. Lespass et LaBoutik
conservent des identifiants et clés liés à Fedow : vider seulement Fedow sur une
instance déjà appairée ne suffit pas. Le changement de configuration ne
réinitialise pas automatiquement ces deux bases.

Sur un hôte déjà initialisé, les scripts de déploiement et de démarrage refusent
une base SQLite manquante sans préparation explicite. Pour une réinitialisation
cohérente décidée séparément, après sauvegarde de l'ancien état et préparation
des trois services, un opérateur peut autoriser le démarrage natif vide :

```bash
sudo python3 /usr/local/lib/tibillet-gala/fedow-sqlite.py prepare-empty \
  /home/ubuntu/TiBillet /var/lib/tibillet-gala/<slug>
```

Cette commande écrit uniquement un marqueur dans le répertoire runtime. Elle
n'efface aucune donnée et refuse si un fichier SQLite ou un marqueur existe
déjà. Après le démarrage sain, le déploiement vérifie la base, prend une première
sauvegarde SQLite puis scelle ce marqueur, même si un ancien backup PostgreSQL
existe. Les redémarrages suivants refusent un fichier absent, vide, incohérent
ou sans configuration Fedow initialisée. Une première installation interrompue
avec une SQLite déjà créée et sans marqueur peut être achevée par
`initialize-storage` après vérification de sa provenance ; `prepare-empty` ne
sert jamais à écraser ce fichier.

Aucun outil de transfert de lignes, aucun `dumpdata/loaddata` et aucun nouveau
module métier n'est introduit. Le risque des signaux natifs pendant un import
reste documenté : `first_block_for_new_asset` et
`transaction_webhook_new_membership` ne filtrent pas `raw=True`. Si un transfert
redevient nécessaire, il devra être qualifié séparément. Un retour à l'ancien
PostgreSQL après de nouvelles écritures SQLite ferait également perdre cet état
récent sans transfert ; aucun changement automatique de moteur n'est prévu.

## Vérifications locales et limites

Les 85 fichiers Python extraits de la référence sont identiques à l'archive.
Les [résultats préparatoires](sqlite-verification-results.json) restent conservés.
Les [résultats de cette implémentation](implementation-verification-results.json)
consignent la comparaison exacte des sources, la suite de tests et les contrôles
de sauvegarde/restauration. Ils utilisent des données fictives et un transport
S3 local ; aucune ressource AWS ni instance distante n'est appelée.

Les dix scénarios du probe natif SQLite WAL ont été rejoués sur une base neuve :
recharge locale, annulation/reprise après erreur locale et Stripe, doublon
simultané de checkout, entrelacement, validation de champ pour actif archivé,
VOID sur plusieurs lieux, checkout historique nul, deux factures avec session
vide, secrets chiffrés. Le doublon ne crédite qu'une fois ; l'autre appel produit
l'`IntegrityError` natif. Le test d'actif archivé caractérise la référence : la
validation du champ l'accepte ; il ne teste pas une fusion complète.

La sauvegarde d'une SQLite dont le WAL reste ouvert conserve les données
commitées. Le contrôle de restauration a réellement démarré un PostgreSQL 13
jetable sans réseau et vérifié la SQLite native isolée. Un ancien backup Fedow
PostgreSQL a aussi été restauré sans conteneur source. Ces essais ne valident
pas la charge du gala, les images déployées, un paiement externe, l'appairage ou
le parcours complet QR/recharge/caisse des trois services. Ce contrôle complet
sur une instance neuve reste à réaliser avant le gala.
