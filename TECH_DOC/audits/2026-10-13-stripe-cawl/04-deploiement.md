# Déploiement de la candidate CAWL

Ce document décrit les étapes à exécuter après revue et qualification. Elles
n'ont pas été exécutées sur la production. Le compte CAWL réel, les accès à sa
sandbox, le contrat et les capacités activées restent à fournir.

## 1. Préparation du marchand

Obtenir auprès de Crédit Agricole / CAWL :

- confirmation de l'API Direct e-commerce utilisée ici ;
- PSPID / merchant ID de test et de production ;
- API key ID et API secret de chaque environnement ;
- webhook key ID et secret de chaque environnement ;
- moyens de paiement, capture directe, refund et Card On File effectivement activés ;
- identité de l'organisation encaissante et compte bancaire de versement.

Créer les clés via le portail marchand. Les secrets doivent passer par le
gestionnaire de secrets prévu pour le gala, sans entrer dans Git ni les logs.
Les appels CAWL exigent HTTPS et l'accès aux hôtes du mode retenu.

Le nouveau parcours transmet ces endpoints avec chaque demande :

| Service | Endpoint |
| --- | --- |
| Encaissement Lespass | `https://<domaine-canonique-tenant>/api/webhook_cawl/` |
| Recharge Fedow | `https://<domaine-fedow>/webhook_cawl/` |

Le domaine de retour stocké sur le lieu Fedow doit correspondre au domaine
canonique Lespass. Le script existant `configure-gala-refill-domain.py` conserve
ce rôle. Le reverse proxy doit accepter les POST des callbacks sans redirection
de domaine ni exigence de connexion utilisateur.

## 2. Configuration du déploiement

Variables pour Lespass et Fedow :

```dotenv
PAYMENT_PROVIDER=cawl
CAWL_TEST=1
CAWL_MERCHANT_ID=<PSPID-test>
CAWL_API_KEY_ID=<identifiant-test>
CAWL_API_SECRET=<secret-test>
CAWL_WEBHOOK_KEY_ID=<identifiant-webhook-test>
CAWL_WEBHOOK_SECRET=<secret-webhook-test>
CAWL_TENANT_SCHEMA=<schema-du-gala>
```

LaBoutik reçoit `PAYMENT_PROVIDER=cawl`, sans clés CAWL. Lespass refuse
l'utilisation du compte marchand si son schéma courant ne correspond pas à
`CAWL_TENANT_SCHEMA`. Aucun compte marchand global de repli n'est choisi pour
un autre tenant.

Les deux secrets de paiement existants (`integrations-stripe-test` et
`integrations-stripe-live`) contiennent chacun les sections `stripe` et `cawl`.
Installer le lecteur runtime compatible sur toutes les EC2 conservées avant
d’ajouter la section CAWL. Exemple de secret test :

```json
{
  "schema_version": 1,
  "stripe": {
    "mode": "test",
    "secret_key": "sk_test_EXAMPLE",
    "publishable_key": "pk_test_EXAMPLE",
    "fedow_webhook_secret": "whsec_EXAMPLE"
  },
  "cawl": {
    "mode": "test",
    "merchant_id": "<PSPID-test>",
    "api_key_id": "<identifiant-test>",
    "api_secret": "<secret-test>",
    "webhook_key_id": "<identifiant-webhook-test>",
    "webhook_secret": "<secret-webhook-test>"
  }
}
```

Le mode de ce secret doit correspondre à Smoke ou Production. Le matériel live
ne doit pas être copié dans Smoke. Le générateur conserve les clés Django,
Fernet, bases, SMTP et domaines existants : changer le prestataire ne justifie
pas de régénérer les identités des portefeuilles ou les clés de signature.

La configuration runtime conserve le nom historique
`SHARED_STRIPE_SECRET_ARN` et les ARN existantes test/live. Le catalogue fixe
`payment_provider=cawl` et le runtime choisit explicitement la section CAWL ;
les champs vides bloquent ce fournisseur, sans modifier les environnements
Stripe. Aucun secret de paiement supplémentaire n’est créé.

## 3. Construire une release de la branche

1. Utiliser le commit revu de `migration/cawl-payments` pour Lespass et les
   extensions Fedow/LaBoutik.
2. Construire les images via les Dockerfiles du dépôt et épingler leurs digests
   dans le manifeste de la candidate.
3. Vérifier que les trois services utilisent la même révision métier attendue.
4. Générer et vérifier l'offre de sources avec les extensions copiées dans les
   images ; le client CAWL commun fait partie de ces sources.
5. Exécuter les tests indiqués dans le rapport et la suite de non-régression
   pertinente avant la promotion.

Les copies d'image sont explicites et les images de base restent épinglées.
Le simple nom d'une branche ne constitue pas un artefact déployé.

## 4. Migrer et configurer en test

Après sauvegarde des bases de l'environnement cible, lancer avec les nouvelles
images et les secrets **de test** :

```sh
docker exec -w /DjangoFiles lespass_django poetry run python manage.py migrate_schemas --noinput
docker exec -w /home/fedow/Fedow fedow_django poetry run python manage.py migrate --noinput
docker exec -w /DjangoFiles laboutik_django poetry run python manage.py migrate --noinput
docker exec -w /DjangoFiles laboutik_django poetry run python manage.py configure_cawl
docker exec -w /DjangoFiles lespass_django poetry run python manage.py configure_gala_refill
docker exec -w /DjangoFiles lespass_django poetry run python manage.py check
```

Adapter le chemin du binaire Poetry à l'image si nécessaire ; la pipeline
existante utilise `/home/tibillet/.local/bin/poetry` pour les services concernés.
La réconciliation Fedow vérifie la présence des paramètres CAWL ; elle ne
prétend pas vérifier les droits financiers du marchand.

Ces migrations ajoutent les tables de journal. Elles ne déplacent ni ne
convertissent les soldes et ne suppriment pas les identifiants Stripe.

## 5. Qualification sandbox obligatoire

| Scénario | Résultat à observer |
| --- | --- |
| Recharge 20 € | Capture CAWL, référence de commande, un CREATION + un REFILL, crédit de 2 000 unités |
| Navigateur fermé après paiement | Le webhook termine le crédit sans retour utilisateur |
| Retour avant webhook | L'interrogation serveur termine le crédit, puis le webhook ne le duplique pas |
| Webhook rejoué / double retour | Une seule vente ou recharge ; même total avant/après replay |
| Paiement autorisé / capture en attente | Aucun crédit ni avantage prématuré |
| Paiement refusé ou abandonné | Solde inchangé ; interface compréhensible et possibilité de reprise contrôlée |
| Montant, devise, marchand ou mode différent | Refus de rapprochement et aucune écriture monétaire |
| Deux demandes simultanées | Une demande en cours par commande ; aucune seconde capture involontaire |
| Adhésion ponctuelle | Moyen CW, dates d'avantage, facture/email et vente LaBoutik correctement rapprochés |
| Réservation | Billets, jauge, montant et TVA conservés ; confirmation indépendante du navigateur |
| Prix libre et zéro euro | Montant saisi transmis exactement ; zéro euro reste hors PSP |
| Crowds | Une contribution payée et un email ; statut de ligne finalisé |
| Refund total/partiel | Demande tracée, statut final confirmé, ligne négative unique et bonne TVA |
| Panne de callback / session expirée | Rapprochement serveur ou traitement opérationnel documenté, sans nouveau débit automatique |

Contrôler également les formulaires, le CSRF, la session utilisateur, les signatures
RSA entre services et les permissions d'administration. Les tests locaux avec
réponses SDK simulées ne remplacent pas ces essais du contrat CAWL.

## 6. Préparer la bascule du gala existant

Avant de sélectionner CAWL en production :

- compter les checkouts Stripe ouverts, les débits SEPA en attente, les refunds
  non finalisés et les ventes non synchronisées ;
- inventorier les abonnements automatiques, les échéances et les itérations ;
- vérifier les soldes par asset, les transactions et la dette de remboursement ;
- terminer les paiements en cours ou établir leur suivi dans l'ancien prestataire ;
- résoudre les exceptions d'abonnements, terminal, reversements et refund de wallet ;
- conserver une sauvegarde restaurable des trois bases et le manifeste de l'ancienne release.

Une recherche de chaînes Stripe dans les fichiers ne donne pas ces volumes de
production. Ils doivent être recueillis dans l'environnement réellement visé.
L'inventaire doit identifier le gala par son domaine, son tenant et son wallet.

## 7. Production et rapprochement

Utiliser le matériel live, `CAWL_TEST=0` et les mêmes associations explicites.
Promouvoir uniquement une candidate qualifiée. Surveiller les captures CAWL,
commandes en attente, erreurs de callback et synchronisations LaBoutik.

Pour les refunds de réservation en attente, lancer périodiquement pour le schéma
configuré :

```sh
poetry run python manage.py reconcile_cawl_refunds --schema <schema-du-gala>
```

Rapprocher trois niveaux : paiement CAWL capturé/refundé, lignes de vente ou
transactions Fedow, puis versement bancaire et frais. Les soldes dépensés en
caisse ne sont pas la même chose que les versements bancaires du PSP.

## 8. Retour arrière

Avant le premier encaissement CAWL, un retour au manifeste et au sélecteur
Stripe peut être qualifié avec les données sauvegardées. Après des encaissements
CAWL, conserver leurs journaux et terminer leur rapprochement. Le retour de
configuration ne transforme pas ces paiements en paiements Stripe.

Ne pas restaurer une ancienne base sur des captures plus récentes sans
reconstitution des opérations intervenues entre les deux états. Un rollback
du code n'annule pas une transaction distante. Le plan de reprise doit conserver
les identifiants, montants et contreparties de chaque prestataire.
