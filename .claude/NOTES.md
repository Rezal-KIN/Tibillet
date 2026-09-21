# Notes techniques — découvertes

Découvertes importantes sur le fonctionnement de ce projet : comportements non documentés, "pièges", intégrations avec des systèmes externes — tout ce qui demande un effort significatif à comprendre et qui n'est pas déductible directement du code. Sert à éviter de re-découvrir la même chose dans une session future ou pour un·e autre développeur·se.

Format suggéré par entrée :
- **Système concerné**
- **Symptôme observé**
- **Cause**
- **Solution / contournement**

---

## Inventaire AWS compte 318629836660 — le compte n'est pas dédié Gala (2026-09-21)

- **Système concerné** : compte AWS `318629836660` ("KIN_REZAL"), cible du plan AWS Gala
  (`docs/aws-access.md` à venir, voir plan `infra/terraform/**`).
- **Symptôme** : le plan suppose un compte dédié Gala avec une seule instance EC2 gala. Un
  inventaire en lecture seule (via un utilisateur IAM bootstrap temporaire, supprimé après
  SSO/Terraform) montre que ce n'est pas le cas.
- **Constat** :
  - Le compte héberge aussi des ressources Méthodo en prod : RDS `methodo` (postgres,
    eu-west-3), bucket S3 `methodo-app`, utilisateur IAM `Methodo-app` avec clé d'accès
    active, security groups liés (`ec2-rds-1`, `rds-ec2-1`, `elasticache-ec2-tibillet-redis`).
  - C'est déjà le compte de management d'une Organization AWS existante (`o-3bri040k1e`),
    avec un compte membre invité `Miniveleur` (149828426208, email thomastabaczka@gmail.com,
    `PENDING_ACTIVATION`) — objet non identifié.
  - `eu-north-1` (Stockholm) contient **4 instances EC2** Tibillet, pas une seule :
    `TibilletBapts` (running), `Tibillet100J_OG` (running), `PPSCP` (stopped),
    `TibilletSiteKfet` (t3.large, stopped) — chacune avec son propre volume EBS gp3. Deux
    snapshots EBS orphelins ne correspondent à aucun volume actuellement attaché.
  - `eu-west-3` a une Elastic IP orpheline (`13.36.118.48`, non associée).
  - IAM Identity Center est **déjà actif** (`ssoins-6656ba18a5bc0eba`, store `d-80677e1879`,
    région eu-west-3), avec un seul utilisateur (`raphael.faure`), un groupe (`admin`), un
    permission set (`AdministratorAccess`, session 1h) assigné directement sur le compte —
    pas encore les permission sets Operator/Elevated ni les 2 autres utilisateurs nominatifs.
  - Aucun secret Secrets Manager n'existe encore dans eu-west-3 ni eu-north-1.
- **Cause** : usage historique du compte antérieur au projet Gala — pas une régression
  introduite par ce repo.
- **Solution / contournement** : voir mémoire personnelle
  `gala-aws-account-actual-state-2026-09-21` pour le détail complet. **Aucune action
  Terraform/IAM destructive tant que la séparation Gala/Méthodo et l'identification des 3
  instances EC2 hors périmètre + du compte `Miniveleur` n'ont pas été validées explicitement
  par l'utilisateur.**
- **Mise à jour (2026-09-21, plus tard)** : Méthodo a bien migré vers un compte AWS distinct
  (`051826693409`) autour du 2026-07-25 (dernière écriture S3 / dernier usage de la clé IAM
  `Methodo-app` à cette date). Les restes dans `318629836660` étaient des données de
  **test** (facture avec adresse "dad"/"dadad", SIRET bidon `12345678900001`, 4 fichiers
  seulement) et le RDS `methodo` avait 0 connexion sur 14 jours. Après confirmation
  explicite de l'utilisateur, ces restes ont été **supprimés** : IAM user `Methodo-app` + sa
  clé, RDS `methodo` (avec snapshot final `methodo-final-snapshot-2026-09-21` conservé par
  sécurité), bucket S3 `methodo-app`. Security groups liés (`ec2-rds-1`, `rds-ec2-1`,
  `elasticache-ec2-tibillet-redis`, `ec2-elasticache-...`) **pas encore nettoyés** (hors
  scope de cette suppression). Ne jamais confondre `318629836660` (Gala) et `051826693409`
  (Méthodo) — toujours vérifier via `aws sts get-caller-identity` avant toute commande.
- **Mise à jour (2026-09-21, identification instance live)** : `eu-north-1` (Stockholm)
  contient 4 instances EC2 Tibillet, mais **une seule est dans le périmètre de ce repo** :
  `TibilletBapts` (i-0cd4e52913c8ae928, 13.61.201.166) — confirmé par résolution DNS de
  `galas-am-aix.rezal.fr`/`fedow.galas-am-aix.rezal.fr`/`cashless.galas-am-aix.rezal.fr`
  (toutes → 13.61.201.166) et recoupé avec l'IP de l'alias SSH `MACHINE-Guinche-Main`.
  **`Tibillet100J_OG` (i-01107b29b967dc1dc, 13.60.93.29) est explicitement HORS PÉRIMÈTRE** —
  instance distincte avec beaucoup de personnalisations que l'utilisateur veut garder intacte ;
  ne jamais la toucher (Terraform import, migration, arrêt, etc.) dans le cadre de ce repo.
  `PPSCP` et `TibilletSiteKfet` (arrêtées) sont d'anciennes instances plus utilisées, mais pas
  encore explicitement validées pour suppression.

---

## Runtime live Bapts — cohabitation effective des stacks 100 jours et V2 (2026-09-21)

- **Système concerné** : EC2 `TibilletBapts` (`i-0cd4e52913c8ae928`, `eu-north-1`), unique
  runtime live de ce repo (`galas-am-aix.rezal.fr` → `13.61.201.166`).
- **Constat (inventaire AWS + SSH strictement lecture seule)** : Bapts exécute non seulement
  Fedow, Lespass et Traefik, mais aussi **`laboutik_100-jours-225`** (Django/Nginx/Redis/
  PostgreSQL 11.5/Memcached) et le preview local **`Lespass-v2`** (Django/Celery/PostgreSQL/
  Redis/Memcached/Nginx, Nginx lié à `127.0.0.1:8090`). Les deux stacks sont `Up` au
  2026-09-21 ; leurs répertoires/Compose sont présents dans `/home/ubuntu/TiBillet`.
- **Ne pas surinterpréter** : cela ne prouve pas que la stack `Laboutik_100-jours-225` est la
  **même chose** que l'EC2 séparée `Tibillet100J_OG` (hors périmètre absolu) ; il s'agit ici
  d'une stack qui tourne sur Bapts, la relation avec l'autre VM reste à établir. Ne jamais
  automatiser l'EC2 `Tibillet100J_OG` ; ne jamais muter cette stack Bapts ou `Lespass-v2`
  avant décision explicite sur leur statut.
- **État hôte utile** : Ubuntu 24.04, Docker 29.3.0, Compose 5.1.0 ; volume root gp3 64 GiB
  non chiffré avec `DeleteOnTermination=false`, aucun snapshot owned observé ; aucune instance
  profile IAM ni inscription SSM. `tibillet-stacks.service` est enabled ; le cron legacy
  `backup_soldes.sh` existe encore. Rien de cela n'a été changé.
- **Git VM** : checkout `Rezal-KIN/Gala-am-Aix-Tibillet` à `25cbc91`; deux assets statiques
  non committés sous `Lespass/www/static/reunion/` — ne jamais les écraser/revertir.
- **Conséquence** : pas de Terraform import/apply, SSM, instance profile, install systemd,
  Secret Manager, Docker pull/up/down/build/restart ni pipeline visant Bapts avant que
  l'utilisateur approuve la liste précise : stacks live à conserver, stacks de test à
  préserver/arrêter, et stacks exclues. La pipeline Test build/publish reste sans cible Bapts.

---

## Pipeline delivery — `deploy-release.sh` exporte des images qu'aucun compose ne consomme (2026-09-20, résolu 2026-09-21)

- **Système concerné** : `tools/runtime/deploy-release.sh` + `Fedow/`, `Laboutik/`, `Lespass/`,
  `traefik/docker-compose.yml`.
- **Symptôme (pas encore observé en prod — trouvé à la relecture)** : `deploy-release.sh`
  exporte `LESPASS_IMAGE`/`FEDOW_IMAGE`/`LABOUTIK_IMAGE`/`TRAEFIK_IMAGE` à partir du manifeste
  de release (digest ECR immuable), mais **aucun `docker-compose.yml` ne référence ces
  variables**. `Fedow/docker-compose.yml` et `Laboutik/docker-compose.yml` utilisent encore
  `tibillet/fedow:${FEDOW_VERSION:-latest}` / `tibillet/laboutik:${LABOUTIK_VERSION:-latest}` ;
  `Lespass/docker-compose.yml` a un `build: context: ./app` (passage V2, voir plus bas) ;
  `traefik/docker-compose.yml` a `image: traefik:latest` en dur. Le garde-fou
  `deploy-release.sh:27` ("release references latest") ne vérifie que la **chaîne du
  manifeste**, pas ce que `docker compose pull && up -d` va réellement tirer — un déploiement
  "release" actuel pullerait `latest`/rebuild depuis les sources, pas le digest validé par la
  pipeline Test.
- **Cause** : les compose files ont été écrits/adaptés (passage Lespass V2, etc.) sans jamais
  être branchés sur le contrat que `deploy-release.sh` suppose déjà (variables `*_IMAGE`).
- **Complication découverte en creusant une correction (overrides additifs par service)** :
  `deploy-release.sh`/`start-stacks.sh`/`preflight.sh`/`stop-stacks.sh` bouclent sur
  `COMPOSE_FILES` (liste `:`-séparée) et appellent `docker compose -f "$compose_file" ...`
  **une fois par fichier, indépendamment** — jamais `-f a -f b` combinés. Un fichier
  `docker-compose.release.yml` additif à côté de chaque base ne serait donc pas fusionné tel
  quel avec la config actuelle des scripts.
- **Ce qui a déjà été vérifié et corrigé séparément** : `Fedow/docker-compose.yml` avait aussi
  un domaine Traefik codé en dur (`Host(\`fedow.galas-am-aix.rezal.fr\`)`) au lieu de
  `${DOMAIN}` comme Laboutik/Lespass — corrigé (bug de copier-coller indépendant du problème
  ci-dessus). Vérifié par SSH (lecture seule) que `Fedow/.env` réel sur la VM a bien
  `DOMAIN=fedow.galas-am-aix.rezal.fr` avant de changer — donc comportement inchangé au
  prochain déploiement.
- **Solution / contournement (implémenté 2026-09-21)** : `COMPOSE_FILES` accepte maintenant
  des groupes séparés par `:`, chaque groupe étant lui-même une liste de fichiers séparés par
  `;` fusionnés en **un seul** appel `docker compose -f a -f b ...` (helper
  `compose_group_args` dans `lib.sh`, utilisé par les 4 scripts). Un `docker-compose.release.yml`
  additif existe désormais pour chaque service (`Fedow/`, `Laboutik/`, `traefik/`,
  `Lespass/`), ne fixant que `image: ${..._IMAGE}`. Pour Lespass, qui a un `build:` dans le
  fichier de base, l'override utilise `build: !reset null` (Compose Spec, nécessite Compose
  >= 2.24 — la VM tourne en v5.1.0) pour retirer complètement `build:` : sans ce reset,
  `build:` aurait continué à gagner sur `image:` et le déploiement aurait silencieusement
  rebuild depuis les sources. **Vérifié** localement avec `docker compose -f base -f release
  config` sur les 4 paires (copies temporaires hors repo, jamais écrit sur la VM ni dans le
  repo) : `image` résout bien vers le digest fourni, et pour Lespass aucune clé `build` ne
  subsiste dans la config fusionnée. `tools/runtime/examples/gala.conf.example` documente le
  nouveau format de `COMPOSE_FILES`.

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
