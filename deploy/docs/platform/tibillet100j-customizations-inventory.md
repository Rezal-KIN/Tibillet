# Inventaire des personnalisations — `Tibillet100J_OG`

## Statut de dérogation

Cet inventaire a été produit par une session SSH **manuelle, strictement en lecture seule**,
le 2026-09-22, sur autorisation explicite ponctuelle de l'utilisateur. `Tibillet100J_OG` reste
listée comme **hors périmètre absolu** dans `deploy/ops/policy/denied-targets.yaml`,
`deploy/docs/platform/scope-and-change-gates.md` et `.claude/NOTES.md` — ces trois fichiers
sont **intentionnellement inchangés** par ce lot. Ce rapport ne vaut pas levée de la politique ;
il ne couvre qu'un inventaire ponctuel, pas un nouvel outillage. Aucune commande de mutation
(Terraform, Docker, systemd, Git, AWS) n'a été exécutée sur cette instance.

Aucune valeur de secret n'est reproduite dans ce document (voir note sur `card_printer/`
ci-dessous).

## Résumé

`Tibillet100J_OG` (i-01107b29b967dc1dc, `eu-north-1`, `13.60.93.29`, instance `running`,
clé AWS `Guinche_Srv_Stockholm` — confirmée identique à celle de `TibilletBapts`) est le
checkout **d'origine** de l'architecture V1 (images Docker Hub `tibillet/*` + répertoires
`custom_patches/` montés en volumes), figé sur le remote
`git@github.com:Rezal-KIN/Gala-am-Aix-Tibillet.git`, branche `main`, commit `ed86ee88` du
2026-05-24. C'est précisément l'architecture que `.claude/NOTES.md` (entrée « Lespass — passage
à la V2 ») décrit comme abandonnée au profit de V2, avec la mention que les patches V1 étaient
« perdus pour l'instant, récupérables via l'historique git si besoin ». Cette machine en est la
source vivante : en plus du commit `ed86ee88`, elle porte **7 fichiers modifiés non commités**
représentant un travail non documenté ailleurs, dont un refactor important de
`Lespass/custom_patches/BaseBillet/views.py` (822 lignes de diff).

Les 4 stacks Compose (`traefik`, `fedow`, `lespass`, `laboutik_100-jours-225`) tournent
(`docker compose ls` : toutes `running`, up depuis 44 h). Les routeurs Traefik déclarent les
**mêmes domaines** que `TibilletBapts` (`galas-am-aix.rezal.fr`, `fedow.galas-am-aix.rezal.fr`,
`cashless.galas-am-aix.rezal.fr`) ; le DNS de ces domaines résout vers Bapts
(`bapts-runtime-inventory.md`), donc cette instance ne reçoit pas de trafic public réel malgré
ses services actifs — c'est un jumeau dormant, pas un second live.

## Catégorie 1 — Déjà versionné (vérifié identique, pas seulement présent)

Vérification faite par diff de contenu (pas par simple présence de nom de fichier) :

| Fichier EC2 | Fichier versionné | Constat |
| --- | --- | --- |
| `Laboutik_100-jours-225/docker-compose.yml` | `deploy/Laboutik_100-jours-225/docker-compose.yml` | identique |
| `Laboutik_100-jours-225/fedow_api.py` | `deploy/Laboutik_100-jours-225/fedow_api.py` | identique |
| `Laboutik_100-jours-225/settings.py` | `deploy/Laboutik_100-jours-225/settings.py` | identique |
| `Laboutik_100-jours-225/validators.py` | `deploy/Laboutik_100-jours-225/validators.py` | identique |
| `Laboutik_100-jours-225/views.py` | `deploy/Laboutik_100-jours-225/views.py` | identique |

Rien à récupérer ici. Note méthodologique : Laboutik n'est pas dans le monorepo (image Docker
Hub `tibillet/laboutik`, pas de submodule source) — cette comparaison est EC2 ↔ overlay
versionné, pas ↔ code source Laboutik upstream, qui n'est pas disponible dans ce dépôt.

## Catégorie 2 — Présent uniquement sur l'EC2, à récupérer

Aucun patch n'est appliqué. Chaque entrée attend un accord explicite séparé ; les entrées
touchant Fedow, paiement, cashless ou auth demandent un accord renforcé (voir Contexte de la
demande utilisateur).

### A. Fedow — endpoint d'enregistrement de carte NFC + nettoyage config bars

- **Fichiers cible** : `deploy/Fedow/custom_patches/fedow_dashboard/urls.py`,
  `deploy/Fedow/custom_patches/fedow_dashboard/views.py`
- **Origine EC2** : diff local non commité (`git diff` sur HEAD `ed86ee88`), 1 ligne (urls.py) +
  86 lignes (views.py — vs HEAD EC2 ; 88 lignes vs la version actuellement versionnée, plus
  ancienne).
- **Contenu** : nouvelle route `POST /dashboard/register_nfc_card/` (vue `register_nfc_card`),
  protégée par un header `X-Gala-Token` comparé à une variable d'environnement
  `ACTIVE_GALA_API_TOKEN` (à définir côté Fedow `.env`, jamais en dur). Crée un `Wallet`
  éphémère + une `Card` (origin_id=1) à partir d'un `first_tag_id` (UID NFC 8 hex), avec
  contrôle d'unicité (409 si déjà enregistrée). Remplace aussi `TRACKED_BAR_LABELS` par une
  nouvelle liste de stands/bars et simplifie `_bar_label_from_raw_name`/`_match_selected_bar`
  (suppression des cas spéciaux "PIAN'S", devenus inutiles avec la nouvelle liste).
- **Justification** : c'est le pendant serveur de l'outil `card_printer/` (item D) — sans cette
  route, l'outil d'enrôlement de cartes NFC ne fonctionne pas.
- **Risque de compatibilité** : faible pour la route elle-même (ajout net, ne modifie rien
  d'existant). Le `TRACKED_BAR_LABELS` est une **donnée propre à un gala précis** (noms de
  stands) plutôt qu'une logique générique — à adapter à la configuration du gala visé plutôt
  qu'à recopier tel quel.
- **Test à exécuter** : POST avec `X-Gala-Token` valide + `first_tag_id` 8 hex → 201 avec
  `qr_url`/`qr_uuid`/`card_uuid` ; sans token ou mauvais token → 403 ; re-post du même
  `first_tag_id` → 409. Vérifier aussi qu'`ACTIVE_GALA_API_TOKEN` est bien lu depuis
  l'environnement (jamais commité) avant toute mise en service.

### B. Laboutik — simplification du nom de domaine nginx

- **Fichier cible** : `deploy/Laboutik_100-jours-225/nginx/laboutique.conf`
- **Origine EC2** : diff local non commité, 2 lignes.
- **Contenu** : `server_name 100-jours-225.cashless.galas-am-aix.rezal.fr;` →
  `server_name cashless.galas-am-aix.rezal.fr;` (retrait du préfixe `100-jours-225.`).
- **Justification** : alignement probable sur le nom de domaine réellement utilisé par le gala
  courant (le préfixe `100-jours-225.` semble être un résidu d'un nommage antérieur).
- **Risque de compatibilité** : si le gala ciblé par ce dépôt utilise encore le sous-domaine
  préfixé, ce changement casserait la règle Traefik (`Host()` ne matcherait plus). À valider
  avec la personne qui gère le DNS avant application.
- **Test à exécuter** : après application, `nginx -t` dans le conteneur, puis vérifier que le
  domaine cible résout et que la règle Traefik associée correspond au DNS réel du gala.

### C. Lespass — arbre `custom_patches/` V1 (absent du dépôt depuis le passage V2)

> Le parcours QR / connexion le plus important de cet arbre est désormais préservé tel quel dans
> `deploy/Lespass/legacy-100j-qr-flow/`, avec une documentation de son comportement et de ses
> garde-fous. Cette archive est documentaire uniquement : elle n'est pas chargée par la stack V2.
>
> Les sept fichiers archivés ont été comparés octet pour octet à leur copie sur
> `Tibillet100J_OG` le 2026-09-22.

- **Fichier cible** : n'existe **nulle part** dans le nouveau dépôt — `deploy/Lespass/` est
  passé en V2 (submodule buildé depuis `TiBillet/TiBillet`, sans mécanisme `custom_patches/`,
  décision du 2026-06-14 documentée dans `.claude/NOTES.md`). Il n'y a donc pas de cible directe
  à patcher : ces fonctionnalités devront être **ré-implémentées contre le code V2 actuel**
  (`Lespass/app/BaseBillet/`), pas copiées-collées telles quelles — les modèles/migrations ont
  changé entre V1 et V2 (`BaseBillet/migrations/0204-0218` divergent, cf. NOTES.md).
- **Origine EC2** : `Lespass/custom_patches/BaseBillet/{urls.py, views.py,
  views_balance_total.py}` (diff local non commité, 822 lignes pour `views.py` à elles seules)
  + `Lespass/docker-compose.yml` (ajout du montage de `views.py`) + le reste de l'arbre
  `custom_patches/` (non modifié localement, donc déjà dans le commit `ed86ee88` : `settings.py`,
  `Administration/admin_tenant.py`, `BaseBillet/refund_models.py`, templates `emails/`,
  `reunion/forms/login.html`, `reunion/partials/navbar.html`, `reunion/views/account/*.html`,
  etc.) — c'est l'ensemble que NOTES.md référence comme « multi-cashless onboarding,
  balance_total/refund_local/qr_card_landing, connexion_with_names, admin Price/Product custom,
  skins/templates custom ».
- **Contenu principal du diff non commité** (le plus significatif, au-delà de ce que NOTES.md
  savait déjà) :
  - `views_balance_total.py` : nouvelle fonction `qr_card_link` (`POST /qr/link/`) — connexion
    directe sans email pour une carte NFC jamais liée (éphémère) : crée/récupère l'utilisateur,
    lie la carte, connecte la session Django, redirige vers la landing page QR. Remplace le
    flow historique par email (`claim`/token signé) pour ce cas précis.
  - `views.py` : suppression du flow `claim` historique (`_extract_claim_qrcode_uuid`,
    `_link_claim_card_to_user`, action `claim`) — remplacé par `qr_card_link` ci-dessus ;
    simplification de `connexion()` (retrait d'un flow front en 2 étapes check/finalize) ;
    ajout de `tenants_admin` dans le contexte `MyAccount` (liste des tenants administrables) ;
    nouvelles actions admin sur `MembershipMVT` : `send_invoice` (renvoi du reçu PDF),
    `ajouter_paiement` (paiement hors-ligne avec passage direct en statut `ONCE`), `cancel`
    (annulation + avoirs comptables optionnels), `renouveller` (pré-remplissage formulaire de
    renouvellement) et leurs `*_reset` associés ; limite par tarif (`price_max_per_user_reached`)
    en plus de la limite par produit ; pagination event-list 50→100 + mise en cache (1h) de la
    page principale + dropdowns filtres (dates/tags/thématiques) calculés sur l'ensemble non
    paginé ; nouvelle page statique `le_faire_festival` ; permission `CanInitiatePaymentPermission`
    sur `QrCodeScanPay` (au lieu de `IsAuthenticated` + check email_valid manuel) ; adhésion
    gratuite (0€) validée directement sans passage Stripe.
  - `urls.py` : route `api/discovery/claim/` (`ClaimPinView`, app `discovery` — non trouvée
    ailleurs dans ce diff, dépendance externe à vérifier), route `qr/link/` (doit être déclarée
    avant le router DRF, comme documenté dans le commentaire du diff).
- **Justification** : fonctionnalités actives de gestion d'adhésions et de cartes cashless pour
  le gala, avec du travail plus récent que le dernier état connu documenté dans NOTES.md.
- **Risque de compatibilité** : **élevé et structurel** — ce code cible l'archi V1 (modèles,
  imports, `FedowAPI` synchrone) ; le portage vers V2 est un travail de réimplémentation, pas
  un simple merge. Touche directement l'authentification (connexion sans email via carte),
  les paiements (Stripe, paiement hors-ligne), et le cashless (liaison carte/wallet) — accord
  utilisateur renforcé requis avant toute réimplémentation, comme précisé dans la demande
  initiale.
- **Test à exécuter** : aucun test automatisé pertinent avant réimplémentation contre le code
  V2. Une fois porté : test du flow `qr_card_link` (carte neuve → saisie email/prénom/nom →
  connexion directe, sans mail) sur un tenant de test ; test des actions admin
  (`ajouter_paiement`, `cancel` avec et sans avoir, `renouveller`, `send_invoice`) sur des
  adhésions de test ; vérifier `price_max_per_user_reached` avec un tarif à quota atteint.

### D. `card_printer/` — outil opérateur d'enrôlement de cartes NFC (hors app, nouveau)

- **Fichier cible** : aucun équivalent dans le dépôt — à créer, par exemple sous
  `deploy/tools/card_printer/` (à discuter : c'est un outil qui tourne sur un poste opérateur
  avec lecteur NFC/imprimante physiques, pas sur le serveur).
- **Origine EC2** : `/home/ubuntu/card_printer/` (hors checkout Git — `card_printer.py`,
  `config_printer.py`, `README.md`).
- **Contenu** : script Python autonome (lecteur NFC ACR122U + imprimante DYMO LabelWriter 450
  via CUPS) qui lit l'UID d'une carte vierge, appelle l'endpoint Fedow `register_nfc_card`
  (item A) pour l'enregistrer, imprime une étiquette QR code + UID, et journalise dans un CSV
  local de secours.
- **⚠️ Secret trouvé** : `config_printer.py` contient un jeton d'authentification **en clair**
  (constante `GALA_TOKEN`), utilisé pour appeler l'endpoint Fedow protégé (item A). Sa valeur
  n'est reproduite nulle part dans ce rapport ni dans aucun fichier committé. Recommandation :
  **roter ce jeton** (le considérer comme potentiellement exposé) avant toute réintégration, et
  le déplacer vers une variable d'environnement / un fichier `.env` non commité au moment du
  portage — jamais en dur dans le script.
- **Justification** : dépendance directe de l'item A ; sans cet outil, la route
  `register_nfc_card` n'a pas de client connu.
- **Risque de compatibilité** : faible pour le code lui-même (script autonome, aucune
  dépendance à l'archi V1/V2 de Lespass). Risque porte uniquement sur le secret à roter.
- **Test à exécuter** : `python card_printer.py --manual` contre un Fedow de dev avec un jeton
  de test (pas le jeton de prod), vérifier la création de wallet/carte et la génération du QR ;
  test d'impression physique nécessite le matériel sur site.

## Catégorie 3 — Legacy/spécifique, à conserver en archive, ne pas réintégrer

- **`extra_hosts` de développement** dans `Lespass/docker-compose.yml` EC2
  (`fedow.tibillet.localhost`, `lespass.tibillet.localhost`, `cashless.tibillet.localhost` →
  `172.17.0.1`) : résidu de configuration de développement local, explicitement commenté
  « only useful for dev purpose » dans le fichier lui-même. Ne pas porter en configuration de
  production.
- **`cartes_gala.csv`** (`/home/ubuntu/card_printer/cartes_gala.csv`) : fichier de sauvegarde
  locale des cartes déjà enrôlées (UID/QR). Non lu, non copié — potentiellement des identifiants
  de cartes déjà en circulation. Hors périmètre de récupération de code ; à traiter séparément
  et prudemment si son contenu doit être migré (donnée, pas customisation applicative).
- **`simulate_delete.py`** (`/home/ubuntu/simulate_delete.py`) : 1 ligne (`import requests`),
  stub sans contenu exploitable. Rien à récupérer.

## Anomalie opérationnelle constatée (hors classement — rien à récupérer, à signaler)

Le crontab `ubuntu` référence deux scripts qui **n'existent ni sur le disque ni dans aucun
dépôt Git** (vérifié : absents de `git ls-files`, absents de `find`) :

```
* * * * * /home/ubuntu/TiBillet/tools/process_gala_provision_requests.py >> .../process_gala_provision_requests.log 2>&1
* * * * * /home/ubuntu/TiBillet/tools/process_laboutik_deletion_requests.py >> .../laboutik_delete_requests.log 2>&1
```

Ces deux tâches échouent silencieusement **chaque minute** (`/bin/sh: 1: <path>: not found`) ;
les fichiers de log correspondants font ~1,6 et ~1,7 Mo (~18 800 lignes chacun), ce qui indique
un échec continu depuis un temps prolongé. Rien à récupérer ici — le contenu de ces scripts
n'existe nulle part et ne peut pas être reconstitué depuis cette instance. Signalé pour
information ; aucune action corrective n'a été prise (aurait nécessité de modifier le crontab,
hors périmètre lecture seule de ce lot).

## Annexe — relevé technique brut (lecture seule, 2026-09-22)

- **AWS** : compte `318629836660` confirmé (`aws sts get-caller-identity --profile
  gala-operator`). Instance `i-01107b29b967dc1dc` (`Tibillet100J_OG`), `running`, `t3.medium`,
  AMI `ami-0e50288dcbe6ca9c1`, lancée `2026-09-20T12:00:13Z`, IP publique `13.60.93.29` (pas
  d'EIP — l'IP peut changer à un redémarrage), VPC `vpc-025a24ec0cc2b7d7f`, SG
  `sg-0869a2698f14ef938` (`launch-wizard-1`), pas d'instance profile IAM. Volume racine
  `vol-0a35769314c803774`, gp3 64 GiB, non chiffré, `DeleteOnTermination=true`.
- **Checkout** : `/home/ubuntu/TiBillet`, remote `git@github.com:Rezal-KIN/Gala-am-Aix-Tibillet.git`,
  branche `main`, HEAD `ed86ee88693600462c63994f084e47c25240aa89` (2026-05-24). 7 fichiers
  modifiés non commités (détaillés ci-dessus), aucun fichier non suivi.
- **Docker** : Docker 29.3.0, Compose v5.1.0. 4 stacks `running` (`traefik`, `fedow`, `lespass`,
  `laboutik_100-jours-225`), toutes up depuis 44 h au moment du relevé. Images taguées (pas
  `latest` pour les apps) : `tibillet/lespass:1.7.15`, `tibillet/laboutik:1.3.8`,
  `tibillet/fedow:1.3.10` — confirmant l'archi V1 (image + `custom_patches/` montés, pas de
  build depuis submodule).
- **Traefik/domaines** : `galas-am-aix.rezal.fr` (Lespass), `fedow.galas-am-aix.rezal.fr`
  (Fedow), `cashless.galas-am-aix.rezal.fr` (Laboutik) — identiques aux domaines de
  `TibilletBapts` ; le DNS pointe vers Bapts, donc cette instance ne reçoit pas de trafic public
  réel malgré ses stacks actives.
- **Systemd/cron** : `tibillet-stacks.service` enabled (même mécanisme de démarrage que Bapts).
  Cron `ubuntu` : `backup_soldes.sh` toutes les 5 min (contenu non lu, convention identique à
  Bapts) + les deux tâches cassées documentées ci-dessus.
- Aucune donnée, secret, `.env`, dump, contenu de `Config.Env` Docker ni `acme.json` n'a été lu
  ou copié pendant cet inventaire (une exception ponctuelle : un jeton en clair trouvé dans
  `card_printer/config_printer.py`, documenté et non reproduit ci-dessus, cf. item D).
