# Reprise pour une revue indépendante

Demande de l'utilisateur : conserver tout dans la branche, puis faire auditer
par un autre agent. Ne pas déployer, fusionner ni modifier une production.
L'enregistrement et le push de `migration/cawl-payments` sont autorisés.

## Références à comparer

```sh
git diff --stat backup/stripe-baseline-2026-10-13...migration/cawl-payments
git diff backup/stripe-baseline-2026-10-13...migration/cawl-payments
```

La baseline est `1e5e60951e30c74fa9dae3f50f9f680ece1f2b72`. La branche reçue
était `work`, sans `main` locale. Les annexes de cet audit se rapportent à cette
baseline et aux deux archives d'images vérifiées, pas à une base de production.

Commencer par le [rapport de vérification](05-verifications.md) et la
[matrice d'exceptions](06-exceptions-actions.md). La branche est une candidate
partielle : paiements ponctuels EUR, recharge, callbacks et remboursements de
réservation. Abonnements automatiques, refunds de wallet, terminals et
reversements fédérés ne sont pas portés.

## Points à examiner en priorité

1. Comparer la sélection du prestataire à chaque chemin des annexes : appel
   direct au SDK, helper, commande, tâche et route. Vérifier les accès Stripe
   résiduels, y compris dans les images natives, et leurs gardes effectives.
2. Vérifier le contrat du SDK et les payloads officiels CAWL avec le marchand
   réellement fourni : hôtes, signatures, statuts, identifiants de maintenance,
   idempotence et expiration des sessions.
3. Examiner les courses entre création de checkout, retour navigateur et
   callback. La commande locale doit conserver la même référence ; une réponse
   réseau ambiguë ne doit pas provoquer une nouvelle capture aveugle.
4. Vérifier les verrous et effets des signaux Lespass, la séparation
   capture/validation, les états de reprise et la livraison des tâches avant ou
   après commit. Les tests séquentiels ne couvrent pas plusieurs workers.
5. Vérifier l'authentification Lespass/Fedow héritée, la propriété du wallet,
   le lieu, le tenant, le marchand et le mode. Vérifier l'unicité du crédit sur
   le ledger réel et le rollback des écritures CREATION/REFILL.
6. Auditer les remboursements partiels, les quantités identiques, les lignes
   multiples et les reprises après une réponse perdue. Vérifier la période
   d'idempotence PSP, les allocations et la confirmation comptable unique.
7. Tester le code `CW` sur LaBoutik native : validation, administration,
   modèle/choix, ventes, refunds, tickets et exports. Examiner l'éventuel besoin
   de migration d'état pour les choix dynamiques de cette extension.
8. Vérifier les dépendances dans les images, l'offre de sources, les nouvelles
   migrations et la compatibilité en mode Stripe. Construire uniquement dans un
   environnement de test autorisé, sans déclencher de pipeline de déploiement.

Produire des constats avec chemin/ligne, scénario reproductible, impact et
correction proposée. Séparer les bugs de cette implémentation, les fonctions
manquantes déjà recensées et les incertitudes du contrat CAWL. Ne pas considérer
les tests simulés comme une preuve de paiement réel ou de parité complète.
