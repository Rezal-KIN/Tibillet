# Reconstruire les sources de cette instance

Les archives sont gratuites et contiennent le code source, les licences et les
mentions originales. `source-manifest.json` identifie la release, les commits et
les empreintes des archives. `SHA256SUMS` permet de vérifier les téléchargements :

```sh
sha256sum -c SHA256SUMS
mkdir lespass fedow laboutik deployment
tar -xzf lespass.tar.gz -C lespass --strip-components=1
tar -xzf fedow.tar.gz -C fedow --strip-components=1
tar -xzf laboutik.tar.gz -C laboutik --strip-components=1
tar -xzf deployment.tar.gz -C deployment --strip-components=1
```

## Ce qui est fourni

- **Lespass** : le code du commit qui a construit l'image applicative.
- **Fedow et Laboutik** : les sources originales au commit vérifié dans l'image,
  avec les fichiers modifiés remplacés par les bind mounts versionnés du gala.
  Les éventuels écarts du script de construction de l'image sont inclus aussi.
- **Déploiement** : Dockerfile Lespass, fichiers Compose/Nginx, patches, exemples
  d'environnement, scripts de construction, de migration et d'installation.
- Chaque application conserve son `pyproject.toml`, son `poetry.lock`, ses
  migrations, templates, fichiers statiques source et licences tierces.

Les données des utilisateurs, dotenvs de production, certificats, clés privées,
logs et dumps ne font pas partie de ces sources. Les scripts de sauvegarde
versionnés et les marqueurs de répertoires nécessaires aux Dockerfiles sont gardés.

## Construction locale des applications

Les Dockerfiles originaux fixent les versions Python : Lespass 3.11, Fedow 3.10,
Laboutik 3.8. Les dépendances système sont installées par ces Dockerfiles ; Poetry
lit les dépendances et leurs versions depuis `pyproject.toml` et `poetry.lock`.

```sh
docker build -f lespass/dockerfile -t gala-lespass-source lespass
docker build -f fedow/dockerfile -t gala-fedow-source fedow
docker build -f laboutik/dockerfile -t gala-laboutik-source laboutik
```

La construction nécessite le téléchargement des images Python, paquets APT et
dépendances Python publiques. Elle ne nécessite ni accès au compte AWS Rezal ni
identifiant de production. Les archives correspondent aux sources applicatives ;
elles ne promettent pas un binaire identique octet pour octet aux images publiées.

## Exécution sur une installation indépendante

1. Copier les `.env.example` de `deployment/deploy/{Lespass,Fedow,Laboutik}/` en
   `.env`, puis renseigner des valeurs propres à l'installation : domaines,
   PostgreSQL, clés d'application générées localement, et intégrations éventuelles.
   Les réglages de production ne sont pas nécessaires et ne sont pas fournis.
2. Fournir le code Lespass à `deployment/deploy/Lespass/app/`, utilisé comme
   contexte de construction par le Compose local. Par exemple, copier le contenu
   extrait de `lespass/` dans ce répertoire vide ; ne pas utiliser son ancien
   pointeur de submodule comme source de la release.
3. Dans les Compose locaux, remplacer les références d'images par les trois
   images construites ci-dessus et adapter les domaines Nginx/Traefik.
4. Créer le réseau Docker `frontend` et les répertoires de données vides avec les
   permissions des utilisateurs applicatifs définis dans les Dockerfiles.
   `start.sh` / `start_services.sh` exécutent les commandes de démarrage.
5. Démarrer Fedow, puis Lespass, puis Laboutik. Les commandes d'initialisation
   sont explicitées dans `deployment/deploy/tools/runtime/deploy-release.sh` :
   `migrate_schemas`, puis `install` et `configure_gala_apex` pour Lespass ; `install`
   pour Laboutik après disponibilité des autres services. Les commandes spécifiques
   aux releases AWS (SSM, ECR, Secrets Manager, sauvegardes S3) servent au déploiement
   Rezal et ne sont pas des prérequis à une installation locale.

Les options existantes et variables de configuration sont décrites dans les
README originaux et `deployment/deploy/README.md`. Lancer les commandes depuis
le répertoire applicatif, via `poetry run python manage.py ...`.

## Accès aux sources après chaque release

`deploy/tools/build-source-offer.py` construit les archives depuis des snapshots
Git fixes. Il applique les fichiers source montés par le Compose de cette même
version du déploiement, vérifie les archives originales par SHA-256 et refuse une
image dont le commit source n'a pas été vérifié. Il n'archive jamais le répertoire
en service ni son historique Git. Les archives d'anciennes releases sont conservées.

Les trois services Nginx exposent `/source/` et les interfaces concernées y donnent
un accès visible. Pour une nouvelle image Fedow/Laboutik, vérifier son commit et
ses écarts avant d'actualiser `deploy/source/image-sources.json`.
