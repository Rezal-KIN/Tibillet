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

Les images Docker sont publiées par TiBillet sur Docker Hub et épinglées à une version testée via la variable `*_VERSION` dans chaque `.env`.

---

## Services

### Fedow (`Fedow/`)
Portefeuille fédéré — gère les actifs monétaires (tokens cashless, fiat), les transactions entre lieux et l'intégration Stripe.

- Image : `tibillet/fedow`
- Compose : postgres + django + nginx
- Patches : [`Fedow/custom_patches/`](Fedow/custom_patches/)

### Lespass (`Lespass/`)
Billetterie, gestion des membres et agenda fédéré. Supporte le multi-tenant (plusieurs lieux sous un même domaine racine).

- Image : `tibillet/lespass`
- Compose : postgres + redis + django + celery + nginx
- Patches : [`Lespass/custom_patches/`](Lespass/custom_patches/)

### Laboutik (`Laboutik/`, `Laboutik_*/`)
Caisse cashless pour les points de vente. Plusieurs instances peuvent tourner en parallèle (une par gala/événement).

- Image : `tibillet/laboutik`
- Compose : postgres + redis + memcached + django + nginx
- Patches : [`Laboutik/settings.py`](Laboutik/settings.py), [`Laboutik/views.py`](Laboutik/views.py), [`Laboutik/validators.py`](Laboutik/validators.py), [`Laboutik/fedow_api.py`](Laboutik/fedow_api.py)

---

## Fonctionnalités additionnelles

### Happy Hour automatique (Laboutik)
Bascule automatiquement sur une grille de prix réduits sur une plage horaire configurable. Les prix sont chargés depuis un fichier JSON monté dans le container.

Variables `.env` concernées : `HAPPY_HOUR_START`, `HAPPY_HOUR_END`, `HAPPY_HOUR_PRICE_FILE`

Fichier de prix à créer sur le serveur : `Laboutik/www/happy_hour_prices.json`
```json
{"biere": 2.50, "soft": 1.50}
```

### Multi-cashless par tenant (Lespass)
Modification de l'endpoint d'onboarding Laboutik pour permettre l'association de **plusieurs caisses** à un même tenant Lespass, sans bloquer si une caisse est déjà configurée.

Patches concernés :
- [`Lespass/custom_patches/ApiBillet/cashless_onboarding.py`](Lespass/custom_patches/ApiBillet/cashless_onboarding.py)
- [`Lespass/custom_patches/ApiBillet/urls.py`](Lespass/custom_patches/ApiBillet/urls.py)

### Dashboard de suivi de gala (Fedow)
Interface temps réel pour suivre les consommations par bar/caisse pendant un événement : totaux par actif monétaire, filtrage par lieu, suivi de session.

Patches concernés :
- [`Fedow/custom_patches/fedow_dashboard/views.py`](Fedow/custom_patches/fedow_dashboard/views.py)
- [`Fedow/custom_patches/fedow_dashboard/urls.py`](Fedow/custom_patches/fedow_dashboard/urls.py)
- [`Fedow/custom_patches/fedow_dashboard/suivi.html`](Fedow/custom_patches/fedow_dashboard/suivi.html)
- [`Fedow/custom_patches/fedow_dashboard/index.html`](Fedow/custom_patches/fedow_dashboard/index.html)

### Synchronisation des dons inter-caisses (Laboutik)
Variable `ENABLE_GIFT_ASSET_SYNC` sur les instances additionnelles pour activer/désactiver la synchronisation des actifs de type don entre les caisses d'un même événement.

### UI personnalisée (Lespass)
Personnalisation de l'interface membre : navbar, page d'accueil, formulaire de connexion, pages de compte (solde, carte, préférences), historique des transactions, email de connexion.

Patches concernés : [`Lespass/custom_patches/BaseBillet/templates/`](Lespass/custom_patches/BaseBillet/templates/)

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
cd Fedow    && docker compose pull && docker compose up -d && cd ..
cd Lespass  && docker compose pull && docker compose up -d && cd ..
cd Laboutik && docker compose pull && docker compose up -d && cd ..
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
- [tibillet/lespass](https://hub.docker.com/r/tibillet/lespass/tags)

---

## Migration vers un nouveau serveur

```bash
# Sur l'ancien serveur — dump des bases
pg_dump -U lespass_user  lespass   > lespass.sql
pg_dump -U fedow_user    fedow     > fedow.sql
pg_dump -U laboutik_user laboutik  > laboutik.sql

# Copier les dumps et les .env vers le nouveau serveur
scp *.sql Fedow/.env Lespass/.env Laboutik/.env user@nouveau-serveur:~

# Sur le nouveau serveur
git clone <url-du-repo> /home/ubuntu/TiBillet
mv ~/Fedow.env    /home/ubuntu/TiBillet/Fedow/.env
mv ~/Lespass.env  /home/ubuntu/TiBillet/Lespass/.env
mv ~/Laboutik.env /home/ubuntu/TiBillet/Laboutik/.env

# Démarrer les services (étape 3 ci-dessus), puis restaurer les bases
docker exec -i fedow_postgres    psql -U fedow_user    fedow    < fedow.sql
docker exec -i lespass_postgres  psql -U lespass_user  lespass  < lespass.sql
docker exec -i laboutik_postgres psql -U laboutik_user laboutik < laboutik.sql
```
