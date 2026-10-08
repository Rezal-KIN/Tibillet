# TiBillet — Configuration déploiement Rezal

Configuration de déploiement de la stack TiBillet pour l'association **Guinche 508-225** (`galas-am-aix.rezal.fr`).

Ce repo contient les fichiers de configuration, patches et personnalisations appliqués par-dessus les images Docker officielles TiBillet. Il ne contient **aucun secret** — les fichiers `.env` sont exclus du dépôt.

---

## Architecture

```
Internet
   │
[Traefik] ← reverse proxy + TLS (réseau Docker externe : frontend)
   ├── lespass.example.fr   → Lespass  (billetterie, membres, agenda)
   ├── fedow.example.fr     → Fedow    (portefeuille fédéré, transactions)
   └── cashless.example.fr  → Laboutik (caisse cashless)
        └── gala.cashless.example.fr → Laboutik instance additionnelle
```

Chaque service tourne dans son propre stack Docker Compose avec un réseau interne dédié (`lespass_backend`, `fedow_backend`, `laboutik_backend`), et se connecte au réseau externe `frontend` pour être exposé via Traefik.

La pipeline construit Lespass depuis ce dépôt. Fedow et LaBoutik sont construits
à partir des images TiBillet exactes épinglées dans leurs Dockerfiles, avec
seulement les petits écarts audités : cartes NFC inconnues, installation
reprenable, emails et liens vers les sources. Aucun fichier Python ou template
HTML n'est monté par-dessus ces applications. Les montages de données, Nginx,
logs, sauvegardes et Redis restent conservés.

Le build produit trois digests ECR et les références de leurs sources. Il
demande les dépôts Fedow/LaBoutik et permissions préparés dans Terraform ;
Foundation doit les appliquer avant le nouveau Test. Les releases historiques
restent associées à leurs anciens commits et ne sont pas réécrites.

---

## Services

### Fedow (`Fedow/`)
Portefeuille fédéré — gère les actifs monétaires (tokens cashless, fiat), les transactions entre lieux et l'intégration Stripe.

- Image : build [`Fedow/Dockerfile`](Fedow/Dockerfile), depuis `tibillet/fedow` épinglée
- Compose : memcached + django (SQLite) + nginx
- Configuration conservée : [`Fedow/settings.py`](Fedow/settings.py)

Le serializer Fedow utilise directement la version native de l'image : son
ancienne copie et son montage ont été retirés. Voir le
[retrait documenté de G](../TECH_DOC/features-enlevees/G-reparations-fedow.md).

### Lespass (`Lespass/`)
Billetterie, gestion des membres et agenda fédéré. Supporte le multi-tenant (plusieurs lieux sous un même domaine racine).

- Build pipeline : depuis le code de ce dépôt, au commit choisi par CodePipeline
- Compose : postgres + redis + django + celery + nginx
- Personnalisations Gala : parcours QR, présentation, accès admin et adaptations de domaine/email documentées dans les audits

### Laboutik (`Laboutik/`, `Laboutik_*/`)
Caisse cashless pour les points de vente. Plusieurs instances peuvent tourner en parallèle (une par gala/événement).

- Image : build [`Laboutik/Dockerfile`](Laboutik/Dockerfile), depuis `tibillet/laboutik` épinglée
- Compose : postgres + redis + memcached + django + nginx
- Sources personnalisées : [`Laboutik/settings.py`](Laboutik/settings.py), [`Laboutik/install.py`](Laboutik/install.py), [`Laboutik/views.py`](Laboutik/views.py), [`Laboutik/validators.py`](Laboutik/validators.py)

Le client Fedow utilise directement le fichier natif de l’image. Les sources
de vues/validation reprennent TiBillet à l’identique, sauf l’enregistrement
automatique de carte conservé. Les anciennes divergences de billets, adhésions,
carte primaire et erreurs sont retirées : voir le
[dossier de retrait LaBoutik](../TECH_DOC/features-enlevees/LaBoutik-ecarts-herites/README.md).

---

## Fonctionnalités additionnelles

### Dépôt CSV des cartes pour les prochains galas

Déposer les lots dans le [dossier S3 privé des cartes](https://s3.console.aws.amazon.com/s3/buckets/tibillet-gala-paris-production-318629836660-backups?region=eu-west-3&prefix=card-stock/uploads/),
puis lancer **Test** dans CodePipeline. La console S3 permet le glisser-déposer.
Utiliser un sous-dossier par génération : `1/gala-am-G1.csv`, `2/white.csv`,
`3/black.csv`, puis `4/nouveau-lot.csv`, etc. Les fichiers restent privés.

Format natif Fedow : UTF-8, séparateur virgule, trois colonnes sans en-tête :
URL QR complète, numéro imprimé, UID NFC. Les anciens classeurs blanc/noir ont
déjà été convertis et vérifiés avec les cartes physiques ; déposer ces CSV
convertis, sans inverser les colonnes. Les identifiants restent ceux imprimés
sur les cartes réutilisées ; les URL utilisent le domaine Gala commun.

Test valide les formats et l'absence de doublons, puis fige les octets dans
des objets nommés par leur SHA-256. Production utilise ce même catalogue,
sans relire le dossier modifiable. Un changement de lots avec le même code
produit une preuve Test distincte. Ajouter un fichier ne lance aucun import
sur un gala existant : il faut exécuter la pipeline puis promouvoir sa release.
Retirer un fichier de ce dossier ne supprime aucune carte déjà importée.

### Prix des articles (Laboutik)
Les prix affichés et contrôlés sont ceux des articles enregistrés en base. La personnalisation happy hour a été retirée ; son ancien fichier de prix et ses variables d’environnement ne sont plus utilisés.

### Dashboard natif (Fedow)
Le dashboard utilise directement les vues, routes et templates de l'image
TiBillet. Les six montages du suivi Gala ont été retirés le 5 octobre 2026 ;
le code précédent est conservé dans le [dossier H](../TECH_DOC/features-enlevees/H-dashboard-financier/README.md).
Les routes Gala `/dashboard/suivi/` et `/dashboard/suivi/data/` disparaissent.
L'accueil réseau reste public selon le comportement natif ; les détails monnaie
et lieu nécessitent un compte administrateur actif.

### Synchronisation des monnaies (Laboutik)
La synchronisation vers Fedow utilise le comportement TiBillet standard : monnaie locale et monnaie cadeau.

---

## Installation

### Prérequis

- Docker + Docker Compose v2
- CLI Infisical installé (voir [tools/INFISICAL.md](tools/INFISICAL.md))
- Un domaine avec les entrées DNS pointant vers le serveur

### 1. Cloner le repo

```bash
git clone <url-du-repo> /home/ubuntu/TiBillet
cd /home/ubuntu/TiBillet
```

### 2. Lancer le script de setup

```bash
bash tools/setup.sh
```

Ce script :
- Crée le réseau Docker `frontend`
- Initialise `traefik/acme.json` (vide, chmod 600) et démarre Traefik
- Configure les credentials Infisical (`~/.infisical-credentials`)
- Exporte les `.env` depuis Infisical pour Fedow, Lespass et Laboutik

> Les certificats TLS sont générés automatiquement par Traefik au premier accès à chaque domaine — pas besoin de les transférer d'une VM à l'autre.

### 3. Démarrer les services

Dans l'ordre (Fedow d'abord, il est la dépendance des autres) :

```bash
cd Fedow    && docker compose build && docker compose up -d && cd ..
cd Lespass  && docker compose build && docker compose up -d && cd ..
cd Laboutik && docker compose build && docker compose up -d && cd ..
```

### 4. Ajouter une instance Laboutik additionnelle

```bash
cp -r Laboutik Laboutik_mon-evenement
cp Laboutik_mon-evenement/.env.example Laboutik_mon-evenement/.env
# Éditer .env : renseigner DOMAIN, GALA_ID, ROUTER_NAME (valeurs uniques)
cd Laboutik_mon-evenement && docker compose pull && docker compose up -d
```

---

## Mise à jour d'un service

```bash
# 1. Éditer la version dans le .env
#    ex : LABOUTIK_VERSION=1.3.9

# 2. Pull la nouvelle image et relancer
cd Laboutik
docker compose pull
docker compose up -d

# Rollback : remettre l'ancienne version dans .env, puis :
docker compose up -d   # l'ancienne image est toujours en cache local
```

Versions disponibles sur Docker Hub :
- [tibillet/laboutik](https://hub.docker.com/r/tibillet/laboutik/tags)
- [tibillet/fedow](https://hub.docker.com/r/tibillet/fedow/tags)

Pour Lespass (build from source), voir la procédure de mise à jour du submodule dans `.claude/NOTES.md`.
