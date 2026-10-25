# Inventaire runtime — TibilletBapts

> Collecté le 2026-09-21 en lecture seule. Aucun service, conteneur, volume, secret, backup, fichier de configuration ou ressource AWS n'a été modifié.

## Identité et infrastructure AWS

| Élément | Valeur |
| --- | --- |
| Compte vérifié | `318629836660` |
| Région | `eu-north-1` |
| Instance | `i-0cd4e52913c8ae928` |
| Nom | `TibilletBapts` |
| État | `running` |
| Type | `t3.medium` |
| AMI | `ami-0e50288dcbe6ca9c1` |
| Lancement | `2026-09-20T11:19:59Z` |
| IP publique / EIP | `13.61.201.166` / `eipalloc-04851c1d274ecb3ff` |
| VPC / subnet | `vpc-025a24ec0cc2b7d7f` / `subnet-0e7a028cb98202b9b` |
| Security group | `sg-0869a2698f14ef938` (`launch-wizard-1`) |
| IMDS | v2 obligatoire |
| Instance profile IAM | absent |
| SSM | absent |

Le volume root est `vol-0b5272ca7cf9ae98d` : gp3, 64 GiB, non chiffré, conservé à la terminaison (`DeleteOnTermination=false`). Aucun snapshot owned de ce volume n'a été trouvé. Il n'est pas géré ni importé par Terraform dans le lot actuel.

## Hôte et boot

- Ubuntu 24.04, kernel `6.17.0-1017-aws`
- Docker `29.3.0`
- Docker Compose `v5.1.0`
- Checkout : `/home/ubuntu/TiBillet`, `Rezal-KIN/Gala-am-Aix-Tibillet`, commit `25cbc91c8217a0e34b6285394ec52c4696748b94`
- `tibillet-stacks.service` est enabled et lance `/usr/local/bin/tibillet-start-stacks` au boot.

Le script de boot actuel relance uniquement Traefik, Fedow, Lespass et `Laboutik_100-jours-225`. Il est legacy et interdit à tout nouvel outillage. Il ne lance pas `Lespass-v2`, même si les politiques `unless-stopped` de ses conteneurs peuvent les relancer avec Docker.

Le checkout contient deux assets statiques non committés :

- `Lespass/www/static/reunion/css/tibillet.css`
- `Lespass/www/static/reunion/js/membership-form.mjs`

Ils doivent être préservés : aucun workflow ne doit les écraser, restaurer ou nettoyer.

## Stacks observées

| Stack Compose | État | Services observés | Statut d'automatisation |
| --- | --- | --- | --- |
| `traefik` | active | Traefik, ports 80/443 publics | active mais ne fait pas partie d'une release applicative future |
| `fedow` | active | Django, PostgreSQL 13, Nginx, Memcached | à approuver comme cible active avant livraison |
| `lespass` | active | Django, Celery, PostgreSQL 13, Redis, Memcached, Nginx | à approuver comme cible active avant livraison |
| `laboutik_100-jours-225` | active | Django, PostgreSQL 11.5, Redis, Memcached, Nginx | préservée, aucune automatisation sans décision explicite |
| `lespass-v2` | active, loopback `127.0.0.1:8090` | Django, Celery, PostgreSQL 13, Redis, Memcached, Nginx | preview locale uniquement, hors livraison |
| `Laboutik/` | aucun conteneur actif | template présent dans le checkout | inconnue / non cible |

La présence de `laboutik_100-jours-225` sur Bapts ne démontre pas son identité avec l'EC2 séparée `Tibillet100J_OG`. L'EC2 `Tibillet100J_OG` reste hors périmètre absolu ; aucune instance, volume, réseau ou stack de cette EC2 ne doit être ciblée.

## Données et sauvegardes

Un cron utilisateur référence le script legacy `/home/ubuntu/backup_soldes.sh`. Son contenu et les données de sauvegarde n'ont pas été lus. Les sauvegardes legacy restent hors du présent lot : ne pas les lancer, modifier, migrer, supprimer ou intégrer à une pipeline.

## Conséquence pour la suite

Avant tout import Terraform, SSM, modification de runtime, Secret Manager, instance profile ou pipeline visant Bapts, l'utilisateur doit valider quelles stacks sont :

1. des services live à conserver et éventuellement promouvoir ;
2. des stacks locales/test à préserver ou arrêter ultérieurement ;
3. des stacks définitivement exclues.

La future pipeline Test reste strictement `Rezal-KIN/Tibillet` → build → ECR digest → manifest, sans contact avec Bapts.
