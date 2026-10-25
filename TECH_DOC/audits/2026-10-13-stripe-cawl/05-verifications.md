# Vérifications locales et limites

État arrêté le 14 octobre 2026 pour commit et revue de branche, à la demande de
l'utilisateur. Les essais ont utilisé des données fabriquées et des bases
locales isolées. Aucun identifiant marchand réel, aucune base de production,
aucune API CAWL distante ni instance déployée n'ont été utilisés.

## Résultats obtenus

| Vérification | Résultat | Portée réelle |
| --- | --- | --- |
| Contrat SDK, signature, montants et tests runtime/source ciblés | 52 tests réussis | Réponses SDK simulées ; SDK officiel installé ; configuration Stripe et CAWL, séparation test/live, secret et tenant, offre de sources |
| Contrat de promotion et réconciliation runtime | 6 tests réussis | Réconciliation locale, idempotence et ARN CAWL du bon environnement ; aucun appel AWS |
| `PaiementCawl` avec Django et PostgreSQL | 8 tests réussis | Création ponctuelle, refus de récurrence/devise, doublon de demande, vente finalisée une seule fois, refus tardif, remboursement demandé/confirmé/refusé |
| Ledger natif Fedow avec Django et SQLite | 5 tests réussis | Capture seule, triple rejeu sans double crédit, montant erroné sans effet, rollback du mint/refill après hash invalide, marchand différent refusé |
| Django `check` lors des deux suites DB | Aucun problème signalé | Chargement des applications et modèles dans les configurations de test |
| `makemigrations cawl_fedow --check --dry-run` | Aucune modification manquante | Extension Fedow uniquement |
| Ruff, sélection `E9,F63,F7,F82` | Réussi sur les fichiers CAWL et points d'intégration inspectés | Erreurs de syntaxe et noms critiques ; ce contrôle ne démontre pas la correction métier |
| Compilation Python et `git diff --check` | Réussis | Syntaxe et propreté du diff |
| Inventaires des archives épinglées | SHA-256 conforme ; aucune erreur de parsing Python | Lecture directe des archives vérifiées, export des emplacements sans contenu de secrets |

**71 tests ciblés réussis au total.** Ce nombre ne représente pas toute la
suite historique TiBillet. Les migrations Lespass ont été exécutées lors de la
création du schéma de test ; le dernier contrôle séparé `makemigrations` Lespass
n'a pas fourni de résultat exploitable avant l'arrêt et n'est pas annoncé comme réussi.

Environnement de ces essais : Python 3.12.14, Django 4.2.30,
`onlinepayments-sdk-python3==10.2.0`, PostgreSQL 17 local pour Lespass, SQLite
pour Fedow, dépendances Lespass issues du lock Poetry. Le module Fedow testé
utilise la source native au commit épinglé dans l'audit.

## Reproduction dans cet espace de travail

Les outils QA et réglages isolés se trouvent hors du dépôt, dans
`/workspace/scratch/cawl-qa-env` et `/workspace/scratch/cawlqa`. Ils ne font pas
partie du commit. Sur une autre machine, préparer des settings de test et des
bases jetables avant de lancer les suites Django.

```sh
python -m pytest -c /dev/null \
  tests/cawl/test_gateway.py \
  deploy/tests/test_gala_credentials.py \
  deploy/tests/test_fedow_webhook_bootstrap.py \
  deploy/tests/test_application_image_sources.py \
  deploy/tests/test_source_offer.py \
  deploy/tests/test_promotion_contract.py -q
```

Pour Lespass, les essais ont lancé `manage.py test PaiementCawl --noinput`
avec `DJANGO_SETTINGS_MODULE=lespass_settings` et
`PYTHONPATH=/workspace/scratch/cawlqa:/workspace/Tibillet`. La base PostgreSQL
QA utilise le socket `/workspace/scratch/cawlqa/pgsocket`, port 55435.

Pour Fedow, les essais ont lancé `python -m django test cawl_fedow --noinput`
avec `DJANGO_SETTINGS_MODULE=fedow_settings` et les chemins Python de QA,
du dépôt, de `deploy/Fedow` et de la source Fedow extraite au commit épinglé.

Les tâches Celery et les réponses de paiement sont simulées dans les tests
Lespass. Les modèles, signaux et écritures de base restent réels. Les tests
Fedow utilisent les modèles et le serializer monétaire natifs, y compris les
contrôles de hash et l'écriture CREATION/REFILL.

## Défauts trouvés et corrigés pendant les essais

- Fixtures de réservation complétées avec l'événement obligatoire et contexte
  tenant restauré après création de l'utilisateur partagé.
- Override des settings installé dans `setUp` : le `setUpClass` de
  `FastTenantTestCase` contourne celui de Django. Cache singleton désactivé
  seulement dans ces tests pour éviter la persistance d'une devise entre cas.
- Ordre de verrouillage des remboursements aligné sur la confirmation de paiement.
- Refus PSP de remboursement vérifié avant l'annulation de la réservation.
- Paiement capturé protégé contre un refus tardif ; statut final des lignes
  conservé après les signaux imbriqués.
- Code `CW` accepté dans le validateur de vente LaBoutik, distinct du code espèces.

## Vérifications non effectuées

Les images n'ont pas été construites ni lancées. La nouvelle application
LaBoutik n'a pas été éprouvée sur sa base native et ses exports. Le parcours
navigateur, les permissions/signatures interservices, la livraison réelle des
webhooks, les captures/refunds CAWL et la concurrence de plusieurs workers
restent à tester. Aucun test de charge ni de parité complète des abonnements,
terminaux ou reversements n'a été effectué.

Ces limites et les fonctions encore absentes sont détaillées dans
[les exceptions et actions](06-exceptions-actions.md). Les tests réussis
permettent une revue du code ; ils ne constituent pas une qualification de production.
