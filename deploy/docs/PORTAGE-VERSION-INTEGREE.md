# Report sur la version intégrée : état au 25 octobre 2026

Branche `tibillet-local-upstream` = version intégrée, c'est-à-dire le `main` de TiBillet/Lespass
au 24 octobre 2026 (`4f135ecfa`, `fedow_core` + `laboutik` dans Lespass, moteur de monnaie
par tenant). Elle remplace la base `archive/main-fedow-import` du 21 septembre, en retard de
359 commits **+ le plan** (`ARCHITECTURE-SELF-HOSTED.md`)
**+ les fichiers de notre travail qui s'ajoutent sans conflit** (commit « report inerte »).

**Rien n'est branché ni testé.** Les fichiers reportés ne sont ni dans `INSTALLED_APPS`, ni dans
`urls.py`, ni appelés : le comportement de la base est inchangé. Ne pas déployer cette branche.

## Reporté tel quel (360 fichiers, ajouts purs)

| Chemin | Rôle |
|---|---|
| `deploy/` | Terraform, buildspec, scripts, documentation des galas (AWS) |
| `releases/` | Manifestes de versions des galas |
| `PaiementCawl/`, `payment_providers/` | Intégration CAWL (recharge, remboursement du solde, webhook) |
| `gala_mail.py` | Courrier de test du gala |
| `Administration/management/commands/configure_gala_{apex,refill}.py` | Configuration du gala |
| `BaseBillet/views_qr_card.py` + 4 gabarits (`qr_landing`, `qr_check_email`, `qr_connexion`, `cawl_refund_status`) | Parcours QR et statut de remboursement |
| `TECH_DOC/audits/2026-10-03-fork`, `2026-10-13-stripe-cawl` | Audits |
| `NOTICE.md` | Mentions du fork |

## Restant à faire (étape par étape, avec les tests à chaque fois)

### 0. Mesurer la base : fait le 25 octobre 2026 (Mac ARM, Docker Desktop)

Pile : `docker-compose.yml` de TiBillet, `.env` copié de `env_example`, certificat mkcert
dans `certs/`. `flush.sh` (migrations, `install` avec poignée de main Fedow, `demo_data_v2`)
passe. Tests : `make test` (`tests/pytest/` et `booking/tests/`), serveur `runserver` actif.

**Résultat : 4 201 réussis, 367 échecs, 4 erreurs, 1 xfail, en 48 min.**

| Cause | Tests | Nature |
|---|---|---|
| Pas de clé Stripe de test (`AuthenticationError: You did not provide an API key`) | 362 (dont les 4 erreurs) | Environnement : `make test` exige une clé `sk_test` et le réseau (voir `make help`) |
| `'Config' object has no attribute 'cache'` | 8 | Mon option `-p no:cacheprovider` ; ils passent sans elle |
| `test_garde_aucun_amount_fois_qty_dans_le_projet` | 1 | **Dû à notre report** : `int(amount * 100)` dans `deploy/Laboutik/`, `deploy/Laboutik_100-jours-225/` et `deploy/Lespass/legacy-100j-qr-flow/` (patches de l'ancien LaBoutik V1) |

Aucun échec n'a été attribué à `fedow_core` ni à `laboutik`. Pour une mesure propre, il reste
à relancer avec une clé Stripe de test. Le classement ci-dessus repose sur le message
d'erreur de chaque test, et quelques tests sont classés « Stripe » d'après leur nom seulement.

Pièges du poste (à reprendre dans la future pipeline locale) :
- `tibillet/fedow:latest` n'existe qu'en amd64 : `platform: linux/amd64` dans un
  `docker-compose.override.yml` local.
- Sous Docker Desktop, `172.17.0.1` (dans `extra_hosts`) ne mène pas à Traefik : remplacer
  par `192.168.65.254` (`extra_hosts: !override`).
- `env_example` ne définit pas `EMAIL_HOST_USER` : `demo_data_v2` échoue à l'envoi du
  récapitulatif (`KeyError`).
- `scripts/lancer_tests.sh` échoue avec le bash 3.2 de macOS (tableau vide sous `set -u`) :
  `make test LANCER="/opt/homebrew/bin/bash scripts/lancer_tests.sh"`.
- Les appels Lespass → Fedow de `send_membership_product_to_fedow` vérifient le certificat
  (CA mkcert inconnue dans le conteneur) : erreur journalisée « non bloquante ».
- `install` et la création de tenant exigent toujours un conteneur Fedow, même en moteur V2.

### 1. Fichiers existant des deux côtés (à réconcilier à la main)
`.dockerignore`, `.gitignore`, `dockerfile`, `Administration/admin/{dashboard,site}.py`,
`AuthBillet/utils.py`, `BaseBillet/{tasks,urls,views}.py`, `TiBillet/{seo_indexing,settings}.py`,
`fedow_connect/fedow_api.py`, `seo/templates/seo/partials/tibillet_community_links.html`.
Comparer avec : `git diff archive/main-fedow-import origin/migration/cawl-payments -- <fichier>`.

### 2. Branchements
`PaiementCawl` et `payment_providers` dans `INSTALLED_APPS` et `urls`, migrations (`PaiementCawl/migrations`),
variables d'environnement CAWL, `PAYMENT_PROVIDER`.

### 3. Recharge et remboursement CAWL sur `fedow_core`
Aujourd'hui `PaiementCawl` crédite et rembourse via l'API du Fedow distant (`fedow_connect`).
Sur la version intégrée : `RefillService.process_cashless_refill` (`fedow_core/PSP_INTERFACE.md`)
et `WalletService.rembourser_en_especes` (`fedow_core/REFUND.md`). Décider quel moteur fait foi
(Fedow distant ou `fedow_core`) pour les cartes du gala.

### 4. CAWL multi-tenant
`PaiementCawl/services.py::gateway()` compare `CAWL_TENANT_SCHEMA` au schéma courant : remplacer par
une liste de tenants autorisés ; vérifier que le webhook retrouve le tenant du paiement.

### 5. Interface des pages du gala (écart plus grand que prévu)
184 fichiers de `BaseBillet` de la branche CAWL **n'existent pas** dans la version intégrée : gabarits
`reunion/` (compte, adhésions, wizard d'événement), thème `faire_festival`, scripts `reunion/js`, images.
Les gabarits QR reportés ci-dessus en dépendent. Vérifier ce que la version intégrée propose à la
place avant de reporter ces pages. Voir aussi `TECH_DOC/features-enlevees/` de la branche CAWL
(fonctions retirées par TiBillet et rétablies dans le fork).

### 6. Cartes du gala
Import des 7 020 cartes (`deploy/tools/runtime/card_stock.py`, `QrcodeCashless`), parcours QR, mails.

### 7. Tests à reporter (non copiés : ils échoueraient à la collecte tant que les branchements manquent)
`tests/cawl/test_gateway.py`, `tests/pytest/test_{configure_gala_apex,configure_gala_refill,fedow_local_transport,qr_card_fedow_e2e,qr_card_onboarding,booking_counter_max}.py`,
`tests/unit/test_gala_mail.py`, `deploy/tests/` (déjà reporté avec `deploy/`).

### 8. Wizard et création d'un événement
Neutraliser le passage Stripe Connect de `TenantCreateValidator.create_tenant` quand
`PAYMENT_PROVIDER=cawl` ; approvisionner `WAITING_CONFIG` ; ajouter le domaine des galas à `DNS_CHOICES`.

## Références
Base : tag `archive/main-fedow-import` (c3bc4879). Travail CAWL : `origin/migration/cawl-payments`.
Filet de sécurité Stripe : `origin/main` (ne pas modifier).
