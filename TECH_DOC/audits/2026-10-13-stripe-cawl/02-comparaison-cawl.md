# Correspondances et différences CAWL

Référence retenue : API Direct de CAWL e-commerce, avec
`onlinepayments-sdk-python3==10.2.0`. Crédit Agricole distribue plusieurs offres :
les identifiants, le PSPID et les capacités activées dans votre contrat doivent
correspondre à cette API avant les essais réels.

## Matrice de fonctions

| Stripe utilisé dans TiBillet | Correspondance CAWL | Décision de migration / différence |
| --- | --- | --- |
| Checkout Session | Hosted Checkout | Commande en centimes et référence UUID créées sur le serveur ; redirection vers la page CAWL |
| Session ID | Hosted checkout ID | Stockage dans `CawlPayment` ou `cawl_fedow.Checkout`, distinct des identifiants Stripe |
| PaymentIntent | Paiement CAWL | Identifiant et statut obtenus depuis l'API du marchand ; ne pas construire un faux PaymentIntent |
| `payment_status=paid` | `CAPTURED` | Seule la capture confirmée déclenche le crédit monétaire. Les états d'autorisation et de capture demandée restent en attente |
| `metadata` et client reference | Merchant reference + données locales | UUID corrélé à une commande locale ; montants et bénéficiaires conservés en base et revérifiés |
| Success URL / cancel URL | Return URL | Le retour déclenche une interrogation serveur. Aucun statut provenant du navigateur ne valide le paiement |
| Webhook Stripe | Webhook CAWL signé | Vérification du corps brut, identifiant de clé, marchand, puis journal unique d'événement |
| Produits et prix Stripe | Montant de la commande | Le tarif vendu et la TVA restent locaux. Le nouveau parcours ne crée pas de catalogue Stripe |
| Montant libre | Montant validé par Lespass avant HCP | Les validateurs actuels acceptent les montants personnalisés de réservation et d'adhésion ; CAWL reçoit ce montant fixe |
| Paiement gratuit | Traitement local existant | Aucun checkout nécessaire pour zéro euro ; le prestataire ne doit pas être appelé |
| Compte Connect par organisation | Compte marchand / PSPID | Aucun équivalent public prouvé de création automatique de comptes Standard. Configuration manuelle du contrat et association explicite au tenant |
| Clé secrète Stripe | API key ID + secret CAWL | Authentification du SDK officiel ; secrets injectés par l'environnement, jamais affichés |
| Test/live Stripe | Environnements CAWL distincts | Hôtes différents, mode enregistré dans chaque paiement et rejet d'un rapprochement avec un compte ou mode différent |
| Refund total / partiel | RefundPayment | Opération locale déterministe, clé d'idempotence, allocations vers les lignes d'origine ; écriture négative après confirmation du refund |
| Refund succeeded | Refund confirmé | `REFUND_REQUESTED` reste une demande. Le webhook ou le rapprochement doit confirmer avant de comptabiliser un remboursement |
| Abonnement Stripe Billing | Card On File / paiements ultérieurs | Un moteur local d'échéances et de recouvrement reste nécessaire. Les tarifs récurrents sont refusés par cette version CAWL |
| `invoice.paid` automatique | Pas de traduction automatique | Factures et événements de renouvellement Stripe restent historiques. Les factures PDF ponctuelles Lespass sont conservées |
| SEPA Stripe | Moyen CAWL selon contrat | Aucun transfert de mandat implémenté. Le réglage `stripe_accept_sepa` n'active pas un mandat CAWL |
| Connect transfers | Versements/acquisition CAWL | Absence d'équivalence démontrée au mécanisme fédéré `transfer.created` ; organiser et qualifier le rapprochement bancaire séparément |
| WisePOS / Terminal | Offre terminal CAWL distincte | L'API e-commerce ne remplace pas un SDK terminal. Les routes terminal Stripe Fedow sont désactivées en mode CAWL |
| Recharge fédérée | Achat CAWL + ledger Fedow natif | Conservation de la monnaie `FED`, du portefeuille émetteur et des soldes ; contrôle du paiement avant `CREATION` et `REFILL` |
| Refund du portefeuille | Débit du ledger + refund PSP | Parcours spécifique à construire ; le refund fédéré Stripe est bloqué en mode CAWL pour éviter une opération sur le mauvais prestataire |
| Vente LaBoutik | Code de moyen `CW` | Choix accepté par le validateur natif et moyen nommé CAWL ; ne pas comptabiliser ces ventes comme Stripe |

## Détails techniques vérifiés

Le SDK utilisé fournit les requêtes typées et l'authentification HMAC. Les hôtes
retenus sont `payment.preprod.cawl-solutions.fr` et
`payment.cawl-solutions.fr`. Les URLs de redirection reçues sont contrôlées contre
l'hôte du mode utilisé. [SDK Python CAWL](https://docs.ecommerce.cawl-solutions.fr/en/integration/how-to-integrate/server-sdks/python).

Hosted Checkout demande un montant avant la redirection. Le paiement créé est
relu via le statut du checkout ; une fois son identifiant connu, les lectures
utilisent le paiement. La session HCP a une durée limitée, ce qui impose un
rapprochement si son identifiant expire avant réception du webhook.
[Hosted Checkout](https://docs.ecommerce.cawl-solutions.fr/en/integration/basic-integration-methods/hosted-checkout-page).

Les webhooks peuvent être redélivrés. Les opérations de maintenance peuvent
changer d'identifiant ; le code conserve donc l'identifiant de capture une fois
le paiement finalisé et traite les refunds dans leur propre journal. Les URLs
de webhook envoyées avec la commande correspondent au service qui l'a créée.
[Webhooks CAWL](https://docs.ecommerce.cawl-solutions.fr/en/integration/api-developer-guide/webhooks).

RefundPayment prend en charge une clé d'idempotence. CreateHostedCheckout ne
figure pas dans la liste publique des méthodes idempotentes : aucun retry
automatique aveugle n'a été ajouté à sa création. Les commandes en cours sont
conservées afin de bloquer une seconde création concurrente.
[Idempotence CAWL](https://docs.ecommerce.cawl-solutions.fr/en/integration/api-developer-guide/idempotent-requests).

Les statuts d'autorisation, capture demandée, paiement capturé et remboursement
demandé ont des significations différentes. Le code ne convertit pas une
demande en succès financier. Les autres moyens de paiement nécessitent de
vérifier leurs états réels dans le contrat et en sandbox.
[Statuts](https://docs.ecommerce.cawl-solutions.fr/en/integration/api-developer-guide/statuses).

Card On File permet des transactions ultérieures. Il ne fournit pas à lui seul
le calendrier, la gestion d'échec, l'arrêt au terme des itérations et le suivi
des avantages de TiBillet. Un abonnement Stripe existant ne peut pas être
transféré par remplacement d'identifiant.
[Cas d'utilisation Card On File](https://docs.ecommerce.cawl-solutions.fr/en/payment-methods-and-features/advanced-features/card-on-file/use-cases).

## Hypothèses encadrées de cette branche

- Encaissements en **EUR** ; une autre devise est refusée.
- Un compte marchand de gala lié à un schéma Lespass précis via
  `CAWL_TENANT_SCHEMA`. La mutualisation de comptes entre organisations n'est
  pas activée implicitement.
- Les identifiants utilisés par Fedow et Lespass doivent désigner le compte
  prévu pour les fonds de ce gala.
- La recharge choisit son montant dans Lespass. La page CAWL sert à payer ce
  montant et ne sert pas de formulaire de montant libre.
- Les comptes et états historiques Stripe restent consultables ; les nouvelles
  opérations sélectionnées en mode CAWL utilisent CAWL.

Les plafonds de recharge actuels sont 0,50 € à 500 € côté serveur ; l'interface
propose 5, 10, 20, 50 et 100 €. Ces valeurs sont des règles de cette branche,
pas une affirmation des minimums ou plafonds contractuels CAWL.
