# Notes techniques — découvertes

Découvertes importantes sur le fonctionnement de ce projet : comportements non documentés, "pièges", intégrations avec des systèmes externes — tout ce qui demande un effort significatif à comprendre et qui n'est pas déductible directement du code. Sert à éviter de re-découvrir la même chose dans une session future ou pour un·e autre développeur·se.

Format suggéré par entrée :
- **Système concerné**
- **Symptôme observé**
- **Cause**
- **Solution / contournement**

---

## Lespass — passage à la V2 (build from source, clean install)

- **Système concerné** : `Lespass/` (Django/django-tenants, billetterie + comptes membres).
- **Contexte** : avant la V2, `Lespass/` tournait sur l'image Docker Hub `tibillet/lespass:${LESPASS_VERSION}`
  avec un dossier `Lespass/custom_patches/` monté par-dessus (urls.py, views.py, admin_tenant.py,
  templates, etc.) + un `Lespass/settings.py` custom monté sur `TiBillet/settings.py`.
- **Changement** : le repo `TiBillet/Lespass` a été fusionné en mono-repo `TiBillet/TiBillet`
  (BaseBillet/ApiBillet/Administration/AuthBillet/PaiementStripe/fedow_connect/onboard/TiBillet sont
  tous au même endroit). `Lespass/app` est maintenant un **submodule git** pointant sur ce mono-repo,
  épinglé sur un commit précis (pas de tags upstream, donc pin par SHA).
  `Lespass/docker-compose.yml` fait `build: { context: ./app, dockerfile: dockerfile }` au lieu de
  `image: tibillet/lespass:...`.
- **Décision (2026-06-14)** : aucun patch/custom de l'ancienne V1 n'a été repris (`custom_patches/` et
  `settings.py` custom supprimés entièrement). Installation V2 "propre", sans dérive. Toutes nos
  customisations gala (multi-cashless onboarding, balance_total/refund_local/qr_card_landing,
  connexion_with_names, admin Price/Product custom, skins/templates custom, `Lespass/settings.py`
  custom) sont **perdues pour l'instant** — récupérables via l'historique git si besoin
  (avant ce commit "passage à la V2"). À ré-implémenter plus tard, en patches neufs contre le code V2
  actuel si nécessaire (ex: `Administration/admin/prices.py`/`products.py` gèrent maintenant
  Price/Product avec de nouveaux modèles `TicketProduct`/`MembershipProduct`/etc — l'ancien
  `admin_tenant.py` patché les ré-enregistrait et aurait crashé au démarrage avec `AlreadyRegistered`).
- **Pin actuel du submodule** : `3a4dedb47d4a116dec45617b10c7a01cb2d902c1` (HEAD de `main` au
  2026-06-11). Pas de tags sur `TiBillet/TiBillet` → toujours pinner par SHA.
- **Mise à jour du pin** :
  ```bash
  cd Lespass/app
  git fetch
  git checkout <nouveau-sha>
  cd ../..
  git add Lespass/app
  ```
  Puis `docker compose -f Lespass/docker-compose.yml build lespass_django lespass_celery` pour
  forcer la reconstruction (sinon l'image en cache n'est PAS reconstruite automatiquement par
  `docker compose up -d` — `build:` ne (re)build que si l'image n'existe pas encore localement,
  ou sur `--build`/`docker compose build` explicite).
- **`dockerfile` en minuscules** : le Dockerfile upstream s'appelle `dockerfile` (pas `Dockerfile`).
  Sur un filesystem case-sensitive (Linux/VM), `build: ./app` seul peut ne pas le trouver — on
  spécifie explicitement `dockerfile: dockerfile` dans le compose.
- **Fedow et Laboutik restent en V1** (images Docker Hub `tibillet/fedow:latest` /
  `tibillet/laboutik:latest`) — Laboutik n'est pas (encore) fusionné dans le mono-repo upstream.
- **Commande de démarrage** : pas de `command:` custom sur `lespass_django`/`lespass_celery` pour
  `lespass_django` — le `CMD` par défaut du Dockerfile upstream (`start.sh`, prod : collectstatic +
  migration conditionnelle + gunicorn :8002) s'applique. `lespass_celery` garde son `command:` celery
  existant.
- **Validation locale** : `docker compose -f Lespass/docker-compose.yml config` n'a pas pu être
  exécuté (pas de binaire `docker` disponible sur cette machine de dev) — YAML validé via
  `python3 -c "import yaml; ..."` uniquement. À valider réellement sur un environnement avec Docker
  avant déploiement VM.

### À faire (phases suivantes, voir `.claude/OBJECTIFS.md`)
- Vérifier la dérive équivalente côté `Fedow/custom_patches/` contre `TiBillet/Fedow` upstream
  (a priori Fedow reste sur l'ancienne archi, mais à vérifier si besoin).
- Tester réellement `docker compose up` (nécessite secrets/.env réels + Docker).
- Réévaluer quelles fonctionnalités custom gala (NFC card claim, refund local, multi-cashless
  onboarding, skins) sont encore nécessaires et les ré-implémenter en patches neufs si besoin,
  contre le code V2 actuel (`Lespass/app/`).
- Script d'installation automatique sur VM vierge (`Administration/management/commands/install.py`
  + `flush.sh` upstream comme référence).
- Déploiement sur `galas-am-aix.rezal.fr` — uniquement après validation + accord explicite.

## Lespass-v2 — stack de PREVIEW de la branche `V2` (alpha, 2026-06-15)

- **Système concerné** : nouveau répertoire `Lespass-v2/`, totalement séparé de `Lespass/` (prod).
- **Pourquoi** : un dev TiBillet a annoncé une refonte majeure ("laboutik/fedow_core/inventaire
  fusionnés") qui vit sur la branche `origin/V2` (tip `bc681a34fb1d08c3ba3fdd715d529742b797388e`,
  2026-05-27). Cette branche est **officiellement déclarée "jamais mergée"** dans
  `TECH_DOC/SESSIONS/M-To-V2/INDEX.md` côté upstream — les features en sont portées une par une
  vers `main` via l'effort "M-To-V2"/"FEDOW_IMPORT" (toujours pas démarré au 2026-06-14, "Lot C-A").
  L'utilisateur veut quand même "tester ce qui arrive" avant le gala (dans 5 mois).
- **Pourquoi un stack séparé et pas un upgrade du pin `Lespass/app`** :
  `BaseBillet/migrations/0204-0218` sont **complètement différentes** entre `main` (notre pin prod
  `3a4dedb47d4a116dec45617b10c7a01cb2d902c1`, déjà appliqué sur 22 schémas tenant) et `V2`. Appliquer
  V2 sur la DB de prod existante casserait ces 22 tenants. Sur une DB neuve, ce problème n'existe pas
  (l'historique V2 est cohérent pour lui-même).
- **Setup** :
  - `Lespass-v2/app` = submodule git séparé sur le même repo `TiBillet/TiBillet`, pinné sur
    `origin/V2`@`bc681a34fb1d08c3ba3fdd715d529742b797388e` (commit figé, pas de tracking de branche).
  - `Lespass-v2/docker-compose.yml` : conteneurs/réseau/volumes préfixés `lespass_v2_*` (pas de
    collision avec les conteneurs `lespass_*`/`fedow_*` de prod sur le même hôte Docker). DB Postgres
    dédiée et vierge. **Pas de label Traefik** — `lespass_v2_nginx` n'écoute que sur
    `127.0.0.1:8090`, accès via tunnel SSH (`ssh -L 8090:127.0.0.1:8090 ...`).
  - `Lespass-v2/.env` (à partir de `.env.example`) : `DOMAIN=v2-preview.localhost`,
    `ADDITIONAL_DOMAINS=localhost,127.0.0.1` (sinon `DisallowedHost` via le tunnel), `DEBUG=True`,
    `MIGRATE=1` au premier démarrage (DB vierge → pas de collision, `migrate_schemas` tourne au
    démarrage via `start.sh`).
  - **Aucun `custom_patches/` repris** : on part de V2 "vanilla" pour avoir une baseline qui boot.
    Le settings.py de V2 a déjà `django-cotton`/`fedow_core`/`channels`/`laboutik`/`inventaire`
    intégrés nativement — pas besoin de patcher `TiBillet/settings.py`.
  - V2 `settings.py` retire plusieurs durcissements de prod (Sentry sampling 0.3 au lieu de 0.0,
    `CELERY_BROKER_TRANSPORT_OPTIONS` anti-duplication de tâches, `SECURE_PROXY_SSL_HEADER`,
    `CanonicalDomainRedirectMiddleware`) — **sans importance pour ce stack de test** (pas de
    Traefik/HTTPS, pas de vrai trafic), mais à garder en tête si jamais on portait V2 en prod un jour.
  - V2 ajoute un `CELERY_BEAT_SCHEDULE` référençant `laboutik.tasks.*` et `seo.tasks.refresh_seo_cache`
    pour les clôtures auto (LNE) — peut générer des warnings Celery si ces tasks ne sont pas
    enregistrées ; attendu pour une branche alpha, à corriger au fil de l'eau ("tu corrigeras").
- **Mise à jour du pin V2** : même mécanisme que `Lespass/app` (voir section précédente), mais sur
  `Lespass-v2/app` et `origin/V2`.
- **Ce stack est une PREVIEW jetable** : DB de test sans rapport avec les vraies données
  d'association. Le stack de prod (`Lespass/`, pin `main`, 22 tenants) n'est touché à aucun moment.
