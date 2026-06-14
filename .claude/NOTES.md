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
