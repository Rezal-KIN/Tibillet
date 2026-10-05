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

Fedow et Laboutik utilisent des images Docker publiées par TiBillet sur Docker Hub, épinglées à une version testée via la variable `*_VERSION` dans chaque `.env`. Lespass est construit depuis le code source (mono-repo `TiBillet/TiBillet`, vendoré en submodule git dans `Lespass/app`, épinglé à un commit précis — voir `.claude/NOTES.md`).

---

## Services

### Fedow (`Fedow/`)
Portefeuille fédéré — gère les actifs monétaires (tokens cashless, fiat), les transactions entre lieux et l'intégration Stripe.

- Image : `tibillet/fedow`
- Compose : memcached + django (SQLite) + nginx
- Configuration conservée : [`Fedow/settings.py`](Fedow/settings.py)

Le serializer Fedow utilise directement la version native de l'image : son
ancienne copie et son montage ont été retirés. Voir le
[retrait documenté de G](../TECH_DOC/features-enlevees/G-reparations-fedow.md).

### Lespass (`Lespass/`)
Billetterie, gestion des membres et agenda fédéré. Supporte le multi-tenant (plusieurs lieux sous un même domaine racine).

- Build : depuis le code source du mono-repo `TiBillet/TiBillet` (submodule git `Lespass/app`, voir `.claude/NOTES.md`)
- Compose : postgres + redis + django + celery + nginx
- Aucun patch custom — installation V2 propre (2026-06-14)

### Laboutik (`Laboutik/`, `Laboutik_*/`)
Caisse cashless pour les points de vente. Plusieurs instances peuvent tourner en parallèle (une par gala/événement).

- Image : `tibillet/laboutik`
- Compose : postgres + redis + memcached + django + nginx
- Sources personnalisées : [`Laboutik/settings.py`](Laboutik/settings.py), [`Laboutik/install.py`](Laboutik/install.py), [`Laboutik/views.py`](Laboutik/views.py), [`Laboutik/validators.py`](Laboutik/validators.py)

Le client Fedow utilise directement le fichier natif de l’image. Les sources
de vues/validation reprennent TiBillet à l’identique, sauf l’enregistrement
automatique de carte conservé. Les anciennes divergences de billets, adhésions,
carte primaire et erreurs sont retirées : voir le
[dossier de retrait LaBoutik](../TECH_DOC/features-enlevees/LaBoutik-ecarts-herites/README.md).

---

## Fonctionnalités additionnelles

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
cd Fedow    && docker compose pull && docker compose up -d && cd ..
cd Lespass  && docker compose build && docker compose up -d && cd ..
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

Pour Lespass (build from source), voir la procédure de mise à jour du submodule dans `.claude/NOTES.md`.
