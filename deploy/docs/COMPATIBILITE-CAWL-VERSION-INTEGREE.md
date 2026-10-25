# CAWL sur la version intégrée : compatibilité (25 octobre 2026)

Comparaison du travail CAWL (`origin/main...origin/migration/cawl-payments`, 40 fichiers
d'application, environ 1 700 lignes hors `deploy/`) avec le `main` de TiBillet/Lespass
(`4f135ecfa`, 24 octobre : `fedow_core` local, `laboutik` multi-tenant, moteur de monnaie
par tenant). Analyse de code uniquement : rien n'est porté ni exécuté.

## Avancement (25 octobre 2026)

- **Bloc A (ventes en ligne) : porté**, commits `66a0fd261` et `9b73b30d2`. TiBillet écrit la vente et
  les avoirs (règlements `CW`) comme pour Stripe ; seuls les appels au prestataire changent.
  Tests : `tests/pytest/test_cawl_ventes.py` (15), `tests/pytest/test_cawl_passerelle.py` (26).
  Aucun nouvel échec dans les tests de vente, d'avoir, de panier et de réservation de
  créneaux en mode Stripe (comparaison test par test avec la mesure de l'étape 0).
- **Bloc D (multi-tenant) : fait.** Un seul contrat CAWL pour toute l'instance (décision du
  25 octobre) ; les lieux autorisés sont listés dans `CAWL_TENANT_SCHEMAS` (virgules). Chaque
  nouvel événement = son schéma ajouté à cette variable.
- **Bloc B (recharge en ligne) : fait** (`PaiementCawl/recharges.py`). Décision du
  25 octobre : UNE monnaie par événement, la monnaie locale (TLF) du lieu, hors
  fédération, donc dépensable seulement dans ce lieu. La recharge en ligne vend le
  produit « Recharge euros » du lieu (créé avec sa monnaie, celui de la borne) par CAWL,
  puis crédite la monnaie avec `TransactionService.creer_recharge`, une fois par paiement
  (transaction REFILL portant l'uuid du paiement). Pas de FED, pas d'appel au Fedow pour
  le crédit. Page : `/my_account/refill_wallet/` (gabarit
  `pages/classic/vues/compte/recharge_en_ligne.html`).
- **Bloc C (remboursement en ligne du solde) : fait** (`PaiementCawl/remboursements.py`,
  bouton existant `/my_account/refund_online/`). Remboursable en ligne = min(solde de la
  monnaie du lieu, recharges CAWL pas encore remboursées), rendu sur chaque paiement CAWL
  d'origine, du plus récent au plus ancien, chacun dans sa transaction. Le reste
  (rechargé sur place) est annoncé « à récupérer au stand » et se rembourse en espèces
  (`rembourser_en_especes`, existant). Comptabilité : vente VIDAGE_CARTE, règlement LE
  positif (jetons repris) et règlement CW négatif (argent rendu, référence CAWL).
  **Clôture** : une monnaie désactivée ou archivée n'est plus remboursée ni créditée, en
  ligne comme au stand (garde ajoutée à `rembourser_en_especes`, en mode CAWL seulement).
- **Bloc F : à faire.** E : à retirer de `deploy/`.

Variables d'environnement d'une instance CAWL : `PAYMENT_PROVIDER=cawl`, `CAWL_TEST` (1 =
préproduction), `CAWL_MERCHANT_ID`, `CAWL_API_KEY_ID`, `CAWL_API_SECRET`,
`CAWL_WEBHOOK_KEY_ID`, `CAWL_WEBHOOK_SECRET`, `CAWL_TENANT_SCHEMAS`. Le webhook à déclarer
chez CAWL est celui de chaque lieu : `https://<domaine du lieu>/api/webhook_cawl/`.

Vérifié le 25 octobre (pile locale démarrée en `PAYMENT_PROVIDER=cawl`, identifiants
factices) : accueil, événement, adhésions, compte, solde, admin et ajout de produit
répondent 200 ; `/api/webhook_cawl/` non signé → 400 ; `/api/webhook_stripe/` → 410.
Suite complète en mode Stripe : aucun nouvel échec par rapport à l'étape 0. Ce signal
reste faible pour le chemin Stripe : sans clé Stripe, ses tests échouent avant d'arriver
au code modifié.

Pièges rencontrés :
- le SDK `onlinepayments` doit être dans l'image (`poetry.lock`) : installé à la main
  dans un conteneur, il disparaît quand le conteneur est recréé ;
- après la recréation de `lespass_django`, redémarrer `lespass_nginx` (sinon 502 : nginx
  garde l'ancienne adresse du conteneur) ;
- `reconcile_cawl_refunds --schema <lieu>` est à planifier (cron ou Celery beat) : le
  minuteur systemd de `deploy/` était propre à AWS.

## En bref

| Bloc | Où il vit aujourd'hui | Verdict |
|---|---|---|
| A. Ventes en ligne (billets, adhésions, crowds) | Lespass : `PaiementCawl/`, accroches dans `Paiement_stripe` et `CreationPaiementStripe` | **À adapter** : les accroches existent toujours, mais la comptabilité des ventes a changé |
| B. Recharge en ligne du porte-monnaie | **Fedow d'origine patché** : `deploy/Fedow/cawl_fedow/` (image `FROM tibillet/fedow`) | **À réécrire** dans Lespass sur `fedow_core` |
| C. Remboursement du solde | Même extension Fedow (`cawl_fedow/refunds.py`) | **À réécrire** dans Lespass sur `fedow_core` |
| D. Multi-tenant | `PaiementCawl/services.py::gateway()` : un seul `CAWL_TENANT_SCHEMA` | **À adapter** (décision à prendre, voir plus bas) |
| E. LaBoutik | `deploy/Laboutik/cawl_laboutik/` (LaBoutik V1, `APIcashless`) | **Obsolète** : le LaBoutik intégré n'en a pas besoin |
| F. Cartes et parcours QR | `views_qr_card.py`, `import_card_stock_fedow.py` : Fedow d'origine | **À réécrire** sur `QrcodeCashless` + `fedow_core.CarteService` |

**Piège de nom** : `cawl_fedow/*` et `import_card_stock_fedow.py` importent `fedow_core.models`
**du dépôt Fedow**. C'est une autre application que le `fedow_core` de Lespass, malgré le nom.
Le travail CAWL actuel n'utilise donc pas le moteur local.

**Réutilisable tel quel** : `payment_providers/cawl.py`, le client SDK `onlinepayments`
(paiement hébergé, lecture du statut, remboursement, vérification du webhook). Il ne dépend
ni de Stripe ni de Fedow.

## A. Ventes en ligne : à adapter

Accroches toujours présentes dans le `main` de TiBillet :
`CreationPaiementStripe` (`PaiementStripe/views.py:42`), `Paiement_stripe.get_checkout_session` et
`update_checkout_status` (`BaseBillet/models.py:4235`, `:4245`),
`Reservation.cancel_and_refund_resa` / `_ticket` (`:3486`, `:3680`), `get_id_price_stripe`,
`onboard_stripe`, `get_stripe_connect_account`, `Webhook_stripe`, `RootConfiguration.get_stripe_api`.

Écarts à corriger :

1. **Signature élargie** de `CreationPaiementStripe.__init__` : `booking`, `accept_sepa`, `vente`.
   L'accroche CAWL les ignore. Or `booking/booking_engine.py:946` (réservation de créneaux) et
   `BaseBillet/services_commande.py:504` (panier) les passent : il faut les transmettre.
2. **Comptabilité des ventes** (`BaseBillet/models_vente.py` : `Vente`, `Reglement`). Le passage
   à PAID écrit la vente, et attend `montant_encaisse` et `moyen` posés avant le `save()`
   (`models.py` vers la ligne 4340). `PaiementCawl.services.update_payment` ne les pose pas :
   il doit renseigner `montant_encaisse` (montant capturé) et `moyen = CAWL`.
3. **Remboursements** : `PaiementCawl/refunds.py::finish_refund` crée lui-même des
   `LigneArticle` négatives. Le `main` passe désormais par les avoirs :
   `ecrire_la_vente_d_avoir_d_une_ligne` / `_d_une_vente` (`BaseBillet/services_vente.py:1183`,
   `:1618`). Les annulations gagnent aussi `annulation_par_l_admin` et `moyen_rembourse`, que
   les enveloppes CAWL doivent transmettre.
4. **Migration** : `0222_alter_lignearticle_payment_method_and_more` est à refaire après
   `0238`. Le code `CW` n'est pas pris ; le `main` a ajouté `NM` (non monétaire).
5. **Rapports caisse** (`laboutik/plan_comptable.py`, `laboutik/reports.py`,
   `laboutik/affichage_des_ventes.py`) : ils traitent `STRIPE_FED` / `STRIPE_NOFED` un par un.
   Il faut leur apprendre `CW`, sinon les ventes CAWL manquent dans les rapports fiscaux.
6. Les tests de comptabilité du `main` (`test_*_ecrit_la_vente.py`,
   `test_avoirs_ecrivent_la_vente.py`, `test_parite_avec_sans_panier.py`) sont le bon filet :
   les faire passer avec `PAYMENT_PROVIDER=cawl` et une passerelle simulée.

## B. Recharge en ligne : à réécrire

- **État du `main` de TiBillet** : la recharge en ligne passe **encore** par le Fedow d'origine
  (`MyAccount.refill_wallet`, `BaseBillet/views.py:2053` → `get_federated_token_refill_checkout`),
  en monnaie fédérée FED et via Stripe. `fedow_core.RefillService.process_cashless_refill`
  (`fedow_core/services.py:1174`) est marqué **« aucun appelant, et c'est voulu »** : il ne
  connaît que le FED local, dont la création est interdite. Il échouerait dès sa première ligne.
- **Notre recharge CAWL** crédite le FED dans un Fedow patché (`cawl_fedow/services.py`).
  Techniquement, la caisse V2 sait dépenser ce FED : elle paie d'abord en monnaies locales, puis
  complète en FED via `_debiter_legacy` (`laboutik/views.py:1629`).
- **Pourquoi ce n'est pas la cible** : le FED est **un seul actif pour tous les tenants**. Sur
  `galas-prod`, toutes les éditions partageraient la même monnaie et le même pot, ce qui
  contredit « une monnaie par édition ». Il faut aussi garder une image Fedow modifiée.
- **Cible** : une recharge CAWL dans Lespass qui crédite la **monnaie locale fiduciaire (TLF) du
  tenant** avec `fedow_core.TransactionService.creer_recharge` (`fedow_core/services.py:898`).
  Elle est idempotente sur l'identifiant du paiement CAWL. Il ne faut pas passer par
  `RefillService`, réservé au FED.
- **Modèle à suivre** : `cawl_fedow/services.py` (création du paiement hébergé, crédit après
  capture vérifiée, verrous, webhook) se transpose presque ligne à ligne. Il faut remplacer
  `Checkout` → un modèle `PaiementCawl`, et `TransactionW2W` → `creer_recharge`.
- **Conséquence** : le Fedow redevient l'image d'origine `tibillet/fedow`, uniquement pour la
  poignée de main et la « place » que le `main` exige de chaque tenant.

## C. Remboursement du solde : à réécrire

- `fedow_core.WalletService.rembourser_en_especes` (`fedow_core/services.py:528`, voir
  `fedow_core/REFUND.md`) rembourse **en espèces au guichet**. Ce n'est pas un remboursement
  bancaire en ligne.
- Notre logique (`cawl_fedow/refunds.py`, environ 250 lignes) répartit le solde sur les
  recharges CAWL d'origine. Elle réserve par une transaction de débit, libère par une
  correction si CAWL refuse, et passe par une file traitée par un minuteur. **C'est le modèle
  à réécrire** sur les jetons TLF du tenant (`fedow_core.Transaction`, action REFUND). La
  sortie comptable passe par les avoirs et ventes du bloc A.
- La commande `reconcile_cawl_wallet_refunds` et le minuteur
  `systemd/tibillet-gala-cawl-refunds.*` deviennent une commande Lespass par tenant (ou une
  tâche Celery beat).

## D. Multi-tenant : décision à prendre

- `gateway()` refuse tout tenant autre que `CAWL_TENANT_SCHEMA`, et les identifiants CAWL
  sont lus dans l'environnement (un seul compte marchand par instance).
- L'adresse du webhook est déjà propre à chaque tenant
  (`https://<domaine du tenant>/api/webhook_cawl/`), et le webhook ne cherche le paiement que
  dans le schéma courant. C'est sain.
- **Question** : un seul contrat CAWL (PSPID) pour tous les événements d'une instance, ou un
  contrat par organisation ?
  - Un seul contrat : liste de tenants autorisés (`CAWL_TENANT_SCHEMAS`) et identifiants
    partagés dans l'environnement. Changement minimal.
  - Un contrat par organisation : identifiants par tenant, chiffrés en base (comme les clés
    Stripe avec Fernet), et une configuration dans l'admin ou le wizard.

## E. LaBoutik : obsolète

`deploy/Laboutik/cawl_laboutik/configure_cawl.py` crée un moyen de paiement `CW` dans
LaBoutik V1 (`APIcashless`). Le LaBoutik intégré lit directement les `LigneArticle` de
Lespass : le point 5 du bloc A suffit. Ce dossier et `deploy/Laboutik_100-jours-225/` sont
aussi ce qui fait échouer `test_garde_aucun_amount_fois_qty_dans_le_projet` (étape 0).

## F. Cartes et parcours QR : à réécrire

- `BaseBillet/views_qr_card.py` lit la carte par `FedowAPI().NFCcard.qr_retrieve`, donc via le
  Fedow d'origine. Le `main` a `QrcodeCashless.CarteCashless` et
  `fedow_core.CarteService.scanner_carte` (`fedow_core/services.py:1309`).
- `deploy/tools/runtime/import_card_stock_fedow.py` écrit dans la base du Fedow d'origine. En
  V2, les 7 020 cartes vont dans `CarteCashless` (Lespass).
- Les gabarits `reunion/views/account/*` (solde, recharge, statut du remboursement) sont à
  refaire dans le système de thèmes du `main` : `pages.services.gabarit_skin("vues/compte/…")`.

## Ordre proposé

1. A : ventes en ligne CAWL avec la comptabilité du `main`, et les tests `ecrit_la_vente`.
2. D : selon la réponse sur le contrat CAWL.
3. B, puis C : recharge et remboursement sur la TLF du tenant.
4. F : cartes et parcours QR.
5. Retirer de `deploy/` ce qui ne sert plus (image Fedow patchée, LaBoutik V1, AWS si validé).
