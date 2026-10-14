# Revue indépendante de la candidate CAWL — 14 octobre 2026

Revue du commit `6c883738` de `migration/cawl-payments` (base `main`
`1e5e6095`), demandée par l'utilisateur après le travail d'un premier agent.
Lecture intégrale du diff applicatif (hors annexes d'inventaire), puis
vérification contre les sources réelles plutôt que par déduction.

## Vérifications factuelles

| Point | Méthode | Résultat |
| --- | --- | --- |
| Appels SDK (`hosted_checkout`, `refunds().get_refunds`, `refund_payment`, `CallContext(idempotence_key=)`) | SDK `onlinepayments-sdk-python3==10.2.0` installé et inspecté | Conformes |
| Vérification des webhooks : en-têtes `X-GCS-*` | `signature_validator.py` du SDK | Recherche insensible à la casse : `request.headers` Django convient |
| Champs `RETURNMAC`, `redirectUrl`, `partialRedirectUrl`, `sessionTimeout` | Classes de domaine du SDK | Conformes |
| Permissions des routes Fedow CAWL | Fedow `1668d94f`, `WalletAPI.get_permissions` | `as_view({...})` fixe `self.action` : `HasPlaceKeyAndWalletSignature` s'applique. La route de retour ajoute en plus un contrôle wallet/lieu |
| `wallet.user` côté Fedow | Code natif (`retrieve_from_refill_checkout`) | Accesseur existant |
| Choix `CW` LaBoutik | LaBoutik `3fdba313`, `MoyenPaiement.categorie` | `max_length=2`, liste `CATEGORIES` partagée par le champ ; le validateur DRF est reconstruit par le setter `choices` |
| Unité de `LigneArticle.amount` | `BaseBillet/models.py` | Centimes entiers : calculs CAWL cohérents |
| Tests sans base | `pytest` local | 40/40 avant correction ; 42/42 après (`tests/cawl`, `deploy/tests` concernés) |
| Ledger Fedow | `manage.py test cawl_fedow` : source Fedow `1668d94f` + settings réels de `deploy/Fedow`, SQLite, Python 3.11 | 6/6 (5 existants + 1 ajouté) après correction des settings |

## Défauts corrigés dans cette revue

| Gravité | Emplacement | Scénario | Correction |
| --- | --- | --- | --- |
| Bloquant | `deploy/Fedow/settings.py` | En mode CAWL, `materialize-runtime-env.py` n'écrit aucune variable `STRIPE_*` dans `fedow.env`. Or les settings Fedow lèvent `STRIPE_KEY nor STRIPE_KEY_TEST` au chargement : **Fedow ne démarre pas**. Révélé en exécutant les tests Fedow, que le premier agent avait lancés avec ses propres settings de QA | Contrôle limité à `PAYMENT_PROVIDER != 'cawl'` |
| Bloquant | `BaseBillet/views.py`, `refill_wallet` | Les boutons « Recharger » appellent la route en htmx : la page complète du formulaire est injectée dans le bouton. Le formulaire est un POST HTML classique, et la réponse `HX-Redirect` affiche une page blanche | GET htmx → navigation complète vers le formulaire ; POST → redirection HTTP vers CAWL ; erreurs → message + redirection |
| Élevée | `PaiementCawl/services.py`, `CreationPaiementCawl` | Si l'appel CAWL échoue après le commit, le paiement reste `PENDING` sans URL. La réservation ou l'adhésion refuse alors définitivement tout nouvel essai (« paiement déjà en cours ») | Paiement passé à `CANCELED` ; erreur de validation explicite |
| Élevée | `PaiementCawl/services.py`, `checkout_session` / `update_payment` | Une page CAWL abandonnée n'expire jamais : l'adhésion renvoie indéfiniment vers une session morte | `sessionTimeout` explicite (60 min) ; au-delà de 75 min sans paiement créé, ou statut HCP abandonné : `expired` / `EXPIRE`. Une capture tardive reste acceptée |
| Moyenne | `PaiementCawl/services.py`, `checkout_session` | Une tentative refusée était vue comme « complete » : page « paiement en cours » pour l'adhésion | Les statuts refusés/annulés ne bloquent plus le réessai |
| Moyenne | `deploy/Fedow/cawl_fedow/services.py` | Même blocage pour la recharge (3 h). La réutilisation sur 3 h pouvait aussi renvoyer une page CAWL déjà expirée | Demande supprimée si aucune URL n'a été remise ; réutilisation limitée à 45 min |
| Moyenne | `PaiementCawl/refunds.py` | Le plafond comparait le nouveau remboursement au montant payé sans compter les remboursements déjà demandés | Plafond = déjà demandé (hors refusés) + nouveau |
| Faible | `cawl_fedow/views.py` et `return_refill_wallet` | Retour navigateur avant la capture : 402 immédiat et message « Payment verification error » alors que le webhook créditera | Attente bornée (environ 6 s, comme le parcours Stripe natif) ; message d'attente en mode CAWL |
| Moyenne | `TiBillet/seo_indexing.py` | Le `noindex` des instances de test reposait sur `STRIPE_TEST`, absent en CAWL : Smoke CAWL serait indexable | `CAWL_TEST` ajouté aux drapeaux |
| Faible | `deploy/tools/runtime/deploy-release.sh` | `configure_cawl` appelé sans condition : une release dont l'image LaBoutik n'a pas la commande échoue | Appel seulement si le conteneur LaBoutik tourne avec `PAYMENT_PROVIDER=cawl` |

Les tests de non-régression correspondants sont ajoutés dans
`tests/cawl/test_gateway.py`, `PaiementCawl/tests.py` et
`deploy/Fedow/cawl_fedow/tests.py`.

## Points ouverts

- **Tests Django Lespass non exécutés pendant cette revue** : il n'y a ni
  PostgreSQL ni Docker sur le poste. À lancer dans la CI ou sur Smoke CAWL.
- La migration `BaseBillet/0222` porte le même numéro que des migrations des
  branches `main-fedow-import` et `integrate_booking_app_with_panier`. Une fusion
  ultérieure demandera une migration de merge.
- Le retour de recharge ignore toujours `start_return_url` (parcours « basic
  card » natif). Sans effet pour le parcours Gala actuel.
- Toutes les réserves du [chapitre 6](06-exceptions-actions.md) restent valables :
  pas de qualification sur le vrai contrat CAWL, pas d'abonnements, pas de
  remboursement de portefeuille, pas de terminal.

## Bloquant externe

Aucun identifiant CAWL (PSPID, clé API, clé webhook) n'est disponible au
14 octobre 2026. La pipeline CAWL peut construire les images. Le déploiement
sur `gala-smoke-cawl` échouera à la lecture du secret
la section `cawl` du secret de paiement test tant qu’elle n’est pas renseignée.


## Reprise de la livraison — 14 octobre 2026

Le premier build réel CAWL a révélé deux contrôles de fabrication restés au
contrat Stripe : la comparaison des settings refusait les modifications CAWL
revues, et l’inventaire des sources Fedow omettait `payment_providers/cawl.py`
pourtant copié explicitement par son Dockerfile. Les corrections conservent
la comparaison intégrale avec les sources natives : seules les substitutions
CAWL exactes de `deploy/source/cawl-settings-overlays.json` sont inversées
avant comparaison. Le snapshot de build inclut le client commun.

Vérification locale : comparaison intégrale avec les archives natives épinglées,
16 fichiers Fedow et 13 LaBoutik explicitement vérifiés ; 198 tests sans base
passés, 3 ignorés. Le succès du build AWS reste une vérification distincte.
