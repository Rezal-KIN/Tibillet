# Investigation des surcharges Fedow et LaBoutik

Investigation du 3 octobre 2026, limitée au code et à des reproductions locales. Aucun accès à une base de production, paiement, débit réel, remboursement réel ou déploiement.

## Conclusion établie

La surcharge `deploy/Fedow/custom_patches/fedow_core/serializers.py` réintroduit une perte d'atomicité sur les recharges générales. **Des conséquences sont reproduites sur une base PostgreSQL locale avec le vrai serializer et le vrai modèle de la référence épinglée**, en remplaçant uniquement le serializer par notre copie pour la variante « overlay ».

LaBoutik perd aussi des protections/fonctions incluses dans sa référence : timeouts GET/POST, traitement des billets, enrichissement des adhésions, distinction panne réseau/carte inconnue et contrat d'erreur des adhésions.

Le remplacement d'une ancienne copie entière explique ces écarts. Il n'existe pas de commit de septembre qui ait explicitement décidé de retirer chacune de ces protections : elles manquent déjà dans les copies importées en `bc5b1a85`. Les changements métier de ces copies remontent à mai, avant les corrections de la référence Fedow datées de juillet/septembre. L'intention de chaque différence n'est pas établie.

## Méthode et limites

- Référence Fedow : `1668d94fb2391cd1b9fef28abf857c356e13207c` ; LaBoutik : `3fdba313c2dea172bfaa6a06ebab05e1caf62490`.
- Archives SHA-256 vérifiées contre `deploy/source/image-sources.json` ; références exactes aussi enregistrées dans `comparison.json`.
- Fedow : Python 3.11, Django 4.2.30, PostgreSQL **15.18 local**. Production déclarée dans Compose : PostgreSQL 13. Ce test ne constitue pas une validation de l'image de production exacte. Migrations réelles exécutées sur la base de test vide, dont contraintes `0025` et `0027`.
- Modules `models.py`, `signals.py` et serializers upstream réels. Variante overlay : import du fichier versionné `deploy/Fedow/custom_patches/fedow_core/serializers.py` avec les mêmes modèles/base.
- Exécution directe de la validation du serializer ; pas d'authentification HTTP/signature ni de webhook Stripe complet exécuté. Les appelants `TransactionAPI.create`, `StripeAPI.validate_stripe_checkout_and_make_transaction` et la configuration PostgreSQL ont aussi été examinés : aucune transaction externe enveloppante trouvée pour ce chemin (`ATOMIC_REQUESTS` absent).
- Le test d'échec injecte une exception avant l'écriture du REFILL, après une CREATION réussie. Le test de concurrence utilise deux connexions PostgreSQL réelles et synchronise la vérification préalable afin que les deux workers lisent « aucun doublon » avant leurs écritures. Ce n'est pas un test de charge.
- LaBoutik : fonctions extraites par AST de la vraie source, avec collaborateurs HTTP/ORM instrumentés et décorateurs omis. La présence des méthodes/appels est également vérifiée dans l'AST. Ce n'est pas une exécution complète du serveur LaBoutik.
- Aucune clé Stripe ou configuration d'instance utilisée. Les connexions réseau externes sont interdites dans la sonde Fedow ; LaBoutik utilise un faux client HTTP.
- Résultats : `fedow-results.json`, `laboutik-results.json` ; scripts reproductibles dans `probes/`. Les montants ci-dessous sont des **valeurs de test**, pas des pertes observées chez un client.

## 1. Recharges générales : création persistante malgré échec de recharge — priorité 1

Fichier : `deploy/Fedow/custom_patches/fedow_core/serializers.py`, `TransactionW2W.validate`.

Le code upstream met CREATION + REFILL dans `_ecrire_la_paire`, sous `atomic()` pour REFILL. Notre fichier crée séparément CREATION puis REFILL en autocommit ; le décorateur `@transaction.atomic` de cette méthode est même commenté.

Exemple testé : recharge de 1 000 centimes ; exception simulée avant REFILL.

| Observation | Référence | Surcharge actuelle |
| --- | --- | --- |
| CREATION persistante après échec | 0 | 1 |
| Solde de l'émetteur après échec | 0 | 1 000 |
| Solde du client après échec | 0 | 0 |
| Relance Stripe du même checkout | Acceptée | Refusée : création déjà faite |
| Relance d'une recharge locale | Acceptée ; émetteur revient à 0 | Acceptée ; client reçoit 1 000 mais émetteur garde 1 000 de la première création |

Cela démontre un défaut de comportement, même avec PostgreSQL. L'absence de retries SQLite, prise isolément, ne permettait pas cette conclusion ; la suppression de l'atomicité, elle, la permet.

Le parcours séparé `TransactionRefilFromLespassSerializer.validate` et le paiement QR ont encore leur `@atomic`. Ne pas généraliser ce défaut à tous les serializers.

## 2. Deux workers, même checkout : transaction doublon refusée, solde néanmoins modifié — priorité 1

Même fichier et méthode. Deux validations concurrentes du même checkout passent la vérification `.exists()` avant de créer.

| Observation après la course | Référence | Surcharge actuelle |
| --- | --- | --- |
| Résultats des workers | 1 succès + 1 IntegrityError | 1 succès + 1 IntegrityError |
| Lignes CREATION / REFILL | 1 / 1 | 1 / 1 |
| Solde du client | 1 000 | 1 000 |
| Solde de l'émetteur | **0** | **1 000** |

La contrainte d'unicité subsiste et bloque le doublon de ligne. Cependant, `Transaction.save()` met à jour les tokens **avant** son INSERT. Sans l'atomicité du serializer, la mise à jour du solde du worker perdant reste commitée quand son INSERT échoue. La présence de la contrainte ne suffit donc pas à garantir la cohérence des soldes dans ce chemin.

Le test ne démontre pas un double paiement Stripe ni un double crédit client en production. Il démontre une dérive du solde émetteur sur une course reproductible localement.

## 3. Protections encore présentes : préciser la première alerte

Le modèle inclus dans la référence conserve :

- les mises à jour par delta avec `F()` des soldes ;
- la contrainte d'unicité partielle `(checkout_stripe, action)` pour CREATION/REFILL ;
- l'unicité du numéro de session Stripe ;
- le contrôle d'une création monétaire existante pour un REFILL, avec appariement par checkout quand il existe.

Le scénario déterministe `CRE_A → CRE_B → REF_A → REF_B`, qui cassait dans l'ancien modèle, aboutit avec **les deux variantes**. Les soldes finaux sont 0 / 1 000 / 2 000. Le retrait de `creation_associee` ne réintroduit donc pas à lui seul l'ancien assert « la dernière transaction doit être une CREATION » : le modèle conserve un filet. La régression prouvée ici est l'atomicité et sa conséquence sur les écritures, pas la disparition de tous les mécanismes de concurrence.

Ces protections sont celles du code/migrations de référence. Leur présence effective dans une ancienne base de production reste à vérifier par inspection en lecture seule lors du contrôle ultérieur.

## 4. Liaison et détachement de carte — priorité 2

Même fichier Fedow :

- **Monnaie archivée dans une fusion** : upstream adapte le champ `asset` à `Asset.objects.all()` pour FUSION. Notre copie conserve `archive=False`. Validation du champ réel : acceptée upstream, refusée overlay. La fusion complète n'est pas exécutée par cette sonde.
- **VOID d'une carte primaire sur deux lieux** : upstream retire seulement le lieu demandeur. La surcharge fait `primary_places.clear()`. Avec deux lieux de test, le VOID upstream conserve le second ; l'overlay ne conserve aucun lieu. Aucun transfert d'argent n'est nécessaire pour cette reproduction.

Conséquences conditionnelles : une monnaie archivée peut empêcher de rattacher une carte ; un VOID peut retirer les autorisations de caisse d'autres lieux de la fédération.

## 5. Deux cas d'entrée supplémentaires — priorité 2/3

- **Garde anti-rejeu sans checkout** : l'overlay lance le filtre anti-rejeu même quand `checkout_stripe=None`. Avec une CREATION FED anormale à checkout NULL construite volontairement dans la base de test, une recharge locale normale est refusée par l'overlay et acceptée upstream. Le modèle interdit normalement la création de cette donnée anormale ; ce cas exige donc une corruption/histoire particulière. Aucune présence de cette donnée en production n'est affirmée.
- **Deux factures Lespass avec identifiant de session vide `''`** : upstream normalise `''` en NULL ; l'overlay le stocke tel quel. Avec deux numéros de facture distincts et metadata UUID valides, upstream crée deux checkouts ; l'overlay crée le premier et lève IntegrityError sur le second. Ce cas dépend de l'entrée vide, pas d'une valeur `None`.

## 6. Réseau LaBoutik — priorité 1/2

Fichier : `deploy/Laboutik/fedow_api.py`, `_get` et `_post`.

L'instrumentation des vrais appels confirme `timeout=(3, 5)` dans la référence, aucun timeout dans notre copie. Requests n'impose alors aucun timeout de connexion/lecture applicatif. Un autre composant peut interrompre la requête ou le worker ; cela ne remplace pas une gestion explicite de l'erreur réseau par LaBoutik.

`_put` n'a de timeout dans **aucune** des deux références : c'est un manque préexistant, pas une suppression par notre overlay.

Fichier : `deploy/Laboutik/validators.py`, `validate_tag_id` ; aussi `views.py`, `check_carte`.

Une ConnectionError injectée dans la consultation de carte déclenche **une tentative de création** dans l'overlay (et un `get_or_create` local), contre zéro upstream. Le `except Exception` interprète des pannes comme des cartes inconnues. La sonde n'affirme pas qu'une création aboutit pendant une panne : l'erreur finale existe toujours ; elle prouve que la mauvaise branche est déclenchée.

## 7. Billets et adhésions LaBoutik — priorité 2

Fichier : `deploy/Laboutik/views.py`.

- L'image de référence garde `Articles.BILLET = 'BI'` et le dispatcher `getattr(self, 'methode_' + ...)`. Notre copie n'a plus `Commande.methode_BI`. La sonde du vrai dispatcher atteint une méthode témoin dans la variante upstream ; elle lève AttributeError dans l'overlay. Une vente portant sur un article BI ne peut donc pas être traitée par cette classe. Aucune vente de billet réelle ni existence d'un tel article en base de production vérifiée.
- `check_carte` et `methode_VT` ne contiennent plus l'appel conditionnel `fetch_adhesions` à Lespass. La couleur Fedow repose encore sur la présence du token d'adhésion ; cette présence ne prouve pas une adhésion actuellement valide. L'option `verifier_adhesion_paiement_nfc` conserve un défaut `False` dans le modèle ; l'impact dépend de son activation.
- `methode_AD` choisit la première carte du membre responsable, plutôt que la carte primaire de la caisse. Pour un membre à plusieurs cartes, la carte envoyée peut ne pas être primaire du lieu. Cas constaté dans le diff ; non reproduit en intégration.

Fichier : `deploy/Laboutik/fedow_api.py`, `Subscription.create_sub`.

Sur une réponse Fedow 400 « carte primaire non valide », la fonction upstream lève une exception explicite ; l'overlay retourne l'entier `400`. L'appelant attend un dictionnaire avec `verify_hash` : il perd l'erreur utile et finit sur une erreur générique. Contrat de fonction reproduit avec une réponse HTTP instrumentée.

## 8. Dashboard Fedow

Le remplacement de `fedow_dashboard/views.py` conserve l'ancien suivi Gala et retire les fonctions de calcul du dashboard réseau de la référence. Les données de noms de bars restent spécifiques à l'ancien événement. Constats statiques du diff ; aucun affichage financier live utilisé pour conclure.

## Suite recommandée, en fonction du choix utilisateur

1. Traiter en premier G : reprendre le serializer upstream de l'image et appliquer seulement les deux ajouts réellement requis (wallet manquant / FIRST), ou retirer entièrement la surcharge après validation du bootstrap. Conserver atomicité, gestion des contraintes et contrôle des recharges. Refaire les deux reproductions de priorité 1.
2. Décider C–F pour LaBoutik, puis repartir de la référence et garder uniquement les ajouts sélectionnés. Retrouver timeouts, gestion d'erreur, billet et adhésions.
3. Décider H pour le dashboard, indépendamment des écritures monétaires.
4. Si l'objectif est de conserver des fonctions tout en supprimant les montages de code, construire des images personnalisées et épinglées. Les volumes des bases et fichiers d'exploitation suivent une autre décision.
5. Contrôle ultérieur : migrations/contraintes réellement appliquées, cohérence soldes/journal, recharges orphelines, synchronisation ventes LaBoutik/Fedow, puis parcours nominaux et défaillants dans un environnement choisi. Aucun rattrapage automatique des soldes n'est autorisé par cet audit.

Le commit d'import `bc5b1a85` contient toute l'infrastructure. Un revert global ne constitue pas un correctif ciblé. L'inventaire A–L décrit les points de retrait et dépendances.
