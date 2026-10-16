# Périmètre CAWL et remboursement du solde

Décision utilisateur du 16 octobre 2026 : le Gala conserve les services et le
déploiement TiBillet de la variante Stripe. CAWL remplace l'encaissement en
ligne et le remboursement des recharges, dans le périmètre ci-dessous.

## Exclusions définitives

Ces fonctions sont **hors périmètre**, sans implémentation CAWL prévue. Elles
ne doivent pas apparaître comme du travail restant avant la production Gala :

- renouvellements automatiques des abonnements et paiements récurrents ;
- terminaux bancaires connectés, dont l'équivalent Stripe Terminal / WisePOS ;
- répartition/reversements entre organisations, dont l'équivalent Stripe Connect.

Les refus explicites existants restent en place. Les lecteurs NFC cashless et
les caisses LaBoutik ne sont pas des TPE bancaires connectés. Le règlement
habituel des encaissements CAWL sur le compte bancaire du marchand ne relève
pas de la répartition entre organisations.

## Remboursement inclus

Le remboursement du **solde restant rechargé en ligne via CAWL** est inclus et
requis. Par exemple, une recharge de 20 € suivie de 12 € d'achats permet de
demander 8 € sur les moyens de paiement des recharges d'origine. Il peut être
réparti sur plusieurs recharges du même portefeuille et du même collectif.
Les monnaies locales, cadeaux, espèces et recharges sur place conservent leur
parcours auprès du collectif ; aucune coordonnée bancaire n'est collectée ici.

Le montant est relu dans Fedow, jamais fourni par le navigateur. Une requête
POST signée par le portefeuille et authentifiée par la clé du collectif porte
un UUID de demande. Le même UUID restitue la demande existante, y compris après
une nouvelle recharge. Le portefeuille ne peut avoir qu'une demande en cours.

Le traitement utilise le journal natif Fedow :

1. Une transaction SQLite atomique réserve le solde avec des écritures `RFD`,
   corrélées aux recharges. La somme réservée cesse immédiatement d'être
   dépensable. Le reste des monnaies du portefeuille est conservé.
2. Le traitement différé lit CAWL, contrôle marchand, test/production, paiement,
   montant et devise, puis soumet chaque remboursement avec un UUID stable et
   une référence d'opération. Aucun appel bancaire ne conserve le verrou SQLite.
3. `REFUNDED` confirme le résultat bancaire. `REFUND_REQUESTED` et les autres
   états intermédiaires restent en traitement : une acceptation API n'est pas
   annoncée comme un remboursement reçu sur le compte bancaire.
4. Un résultat définitif `REJECTED` ou `CANCELLED` restitue exactement une fois
   la somme avec une écriture native `COR`. Le journal reste append-only ;
   aucune modification directe d'un montant de token ne simule un remboursement.
5. Une panne, un délai réseau ou une réponse incohérente maintient la réservation.
   La reprise commence par chercher l'opération chez CAWL. Le même remboursement
   ne peut être resoumis avec sa clé que pendant les 23 premières heures ;
   au-delà, la lecture continue mais toute nouvelle soumission est bloquée pour
   rapprochement humain. Une absence dans une liste ne prouve pas un échec.

Une demande qui ne peut pas être adossée intégralement à des recharges CAWL
connues du portefeuille et du collectif est refusée avant tout débit. Un
remboursement effectué manuellement dans le portail bancaire, non retrouvé dans
le journal, impose un rapprochement : ne pas ajouter une deuxième opération.

## Exécution et suivi

Le bouton « Demander un remboursement » confirme une demande par POST avec
protection CSRF. La page affiche montant demandé, montant confirmé, montant
en cours et montant recrédité en cas de refus. Le mail initial confirme
l'enregistrement de la demande, sans annoncer un succès bancaire anticipé.

Le service `tibillet-gala-cawl-refunds@<gala>.service`, déclenché toutes les
30 secondes après la fin du traitement précédent, exécute dans Fedow :

```sh
poetry run python manage.py reconcile_cawl_wallet_refunds --limit 100
```

Il n'est activé que pour un gala CAWL après migrations, santé des services,
sauvegarde et enregistrement du manifeste déployé. Le script refuse de traiter
une image différente de ce manifeste. Les webhooks signés de remboursement
déclenchent également une lecture de l'état bancaire. Leur répétition ne crée
aucune écriture financière supplémentaire.

Pour une demande en `REVIEW`, conserver les écritures et leur référence, puis
rechercher cette référence dans les remboursements du paiement d'origine.
Relancer la commande ne soumet pas une nouvelle opération après l'expiration
de la fenêtre d'idempotence. Ne jamais libérer une réservation sur la seule
base d'un timeout ou d'une absence de réponse. Un changement de marchand ou de
mode doit être résolu avec le compte d'origine avant toute reprise.

## Qualification

Le code et les tests automatisés ne constituent pas une qualification bancaire
réelle. Les preuves de test et de déploiement sont consignées dans le bilan de
la livraison. La validation CAWL en production et les essais du matériel de
caisse restent nécessaires avant utilisation réelle.

Références : [opérations de remboursement CAWL](https://docs.ecommerce.cawl-solutions.fr/en/integration/api-developer-guide/maintenance-operations),
[idempotence, garantie minimale de 24 heures](https://docs.ecommerce.cawl-solutions.fr/en/integration/api-developer-guide/idempotent-requests),
[webhooks CAWL](https://docs.ecommerce.cawl-solutions.fr/en/integration/api-developer-guide/webhooks).
