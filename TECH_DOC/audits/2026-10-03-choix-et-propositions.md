# Choix utilisateur et propositions après l'audit des volumes

**Document historique de proposition.** La décision ultérieure privilégie le
retour au code TiBillet vanilla : D et F sont retirés, B est conservé comme guide
de connexion rapide. La proposition de réimplémenter D est abandonnée. Les choix
à jour, les retraits C/D/F et leur vérification textuelle sont dans
[features-enlevees](../features-enlevees/README.md).

État local du 3 octobre 2026. Le snapshot initial dans `2026-10-03-fork/`
reste intact. Ce document conserve les décisions et les propositions à examiner
avant d'intégrer D, E et H.

## Direction retenue

L'utilisateur souhaite que le code exécuté soit décrit par des images versionnées,
plutôt que remplacé après démarrage par des fichiers montés depuis l'hôte.

La cible proposée est : images personnalisées Fedow/LaBoutik construites depuis
les références épinglées, petits modules de personnalisation versionnés, configuration
applicative lisant l'environnement, et images Nginx contenant leur configuration.
La pipeline devra construire et tester ces images avant de produire un manifeste
de release avec leurs digests. Elle construit actuellement l'image Lespass ;
la construction des images personnalisées Fedow/LaBoutik reste à préparer.
Les sources distribuées devront correspondre à cette nouvelle construction.

La persistance des bases et des médias reste nécessaire indépendamment des images.
Les secrets continuent d'être fournis par le mécanisme de configuration runtime.
Ce changement d'architecture n'est pas encore implémenté ni déployé.

## Décisions par élément

| ID | Décision reçue | État dans ce lot |
| --- | --- | --- |
| A | Garder le parcours QR | Conservé |
| B | Expliquer le guide d'accueil | Aucune modification |
| C | Enlever le happy hour | Retrait local préparé et testé |
| D | Garder la limite de caisse, proposer une intégration simple avant action | Proposition ci-dessous, sans implémentation |
| E | Garder l'enregistrement des cartes inconnues, proposer avant action | Proposition ci-dessous, sans implémentation |
| F | Pas une priorité pour l'utilisateur | Aucun changement ; option désactivée par défaut dans le code, valeur runtime non inspectée |
| G | Expliquer les réparations et le défaut découvert | Proposition de correction, aucune modification |
| H | Garder le dashboard, expliquer les risques et proposer avant action | Proposition ci-dessous ; utilisateur a confirmé que sa seconde mention de H concerne bien H |
| I | Expliquer la configuration Python | Aucune modification |
| J / K | Aucun choix explicite reçu | Aucune modification |
| L | Expliquer les risques de configuration Nginx | Aucune modification |

## C : retrait local autorisé

Introduction dans le fork : `bc5b1a85`, depuis une personnalisation historique
déjà présente dans `30c571bc`. Le retrait est ciblé sur l'état courant :

- Suppression des calculs horaires, du chargement JSON et du remplacement des prix
  du payload terminal dans `deploy/Laboutik/views.py`.
- Restauration de la seule méthode `validate_articles` à la référence LaBoutik
  `3fdba313c2dea172bfaa6a06ebab05e1caf62490` ; les prix contrôlés sont ceux des articles en base.
- Retrait des variables happy hour de `.env.example` et actualisation du README.
- Retrait des scripts dédiés `hh_seed.py` et `hh_alias_fix.py` de l'outillage courant.
  Le premier pouvait aussi modifier le catalogue ; ils ne sont plus proposés à l'exécution.
  Leur version originale reste dans l'historique Git.

Aucun fichier de prix runtime, article, transaction ou solde n'a été supprimé ni
modifié en base. Les archives des 100J et le snapshot d'audit restent intacts.
Les fichiers applicatifs restent provisoirement livrés par les montages actuels ;
la migration de D/E et des autres personnalisations vers des images nécessite la
proposition puis son implémentation.

Validation : cinq tests de fonctions réelles avec ORM/HTTP instrumentés (prix
affichés, total nominal, ancien prix remisé refusé, total incorrect, retour de
consigne), comparaison AST de la méthode de validation avec la référence épinglée,
et contrôle des autres méthodes/fonctions. Les neuf tests existants de publication
des sources sont également exécutés. Ce n'est pas un test de caisse déployée.

## B : guide d'accueil

Dans `BaseBillet/templates/reunion/views/home.html`, une section présente trois
étapes : récupérer une carte NFC à l'entrée, la recharger par QR ou en caisse,
puis payer aux bars. Le bouton adhésion ouvre le panneau de connexion quand
l'utilisateur n'est pas connecté ; il ouvre `/memberships/` quand il l'est.
Il s'agit d'interface Lespass construite dans l'image, sans écriture financière.
Une erreur de template pourrait casser cette page ; le risque métier est faible.

## D : limite de deux terminaux de caisse — proposition

Conserver la règle : au troisième terminal autorisé sur la caisse, le plus ancien
perd son accès à cette caisse. La logique actuelle utilise une liste Memcached,
sans verrou autour des lectures/écritures, et désactive globalement l'appareil.

Proposition : un module LaBoutik dédié avec une petite table de sessions de caisse
(terminal, point de vente, date d'entrée), et un verrou PostgreSQL sur le point de
vente dans une transaction courte pour inscrire/retirer les sessions. L'admission
se fait après validation de la carte primaire et des droits sur ce point de vente.
Un contrôle de session avant les nouvelles opérations de caisse empêche un
terminal évincé de continuer à l'utiliser. L'éviction ne désactive pas le terminal
pour les autres usages. La clôture/sortie et le changement de point de vente
libèrent sa session ; une reconnexion par carte primaire réinscrit le terminal.

L'exemption admin utilise une liste explicite d'identifiants de terminaux dans la
configuration runtime, plutôt que leur nom commençant par `admin`. La règle et
le module sont inclus dans l'image ; seule la liste d'identifiants varie par instance.
Une migration additive serait requise pour cette petite table.

Tests à faire avant intégration : trois admissions simultanées, FIFO, exemption,
reconnexion, refus d'une opération après éviction, refus d'admission sans droit
de carte primaire, et absence d'effet sur les autres points de vente.

## E : carte inconnue — proposition

Créer un helper partagé pour le scan et la validation de paiement :

1. Interroger Fedow depuis un terminal authentifié du lieu.
2. Enregistrer une carte uniquement sur une réponse 404 carte inconnue.
3. Réutiliser le même enregistrement local et son UUID en cas de nouvelle tentative.
4. En cas de conflit d'unicité confirmé à la création distante, relire la carte et
   vérifier son identité plutôt que considérer toute erreur comme un succès.
5. Sur panne réseau, timeout, signature invalide ou refus d'accès, signaler l'erreur
   et ne pas tenter de création. Restaurer les timeouts de la référence réseau.

Cette opération n'ajoute aucun crédit : l'enrôlement et la recharge restent deux
opérations distinctes. Les appels HTTP et les écritures locales ne constituent
pas une transaction distribuée ; un échec intermédiaire doit être visible et
reprenable avec la même identité, sans promesse d'annulation atomique interservices.
Helper et petits points d'appel sont construits dans l'image LaBoutik.

Tests à faire : 404 réel, 403, timeout, erreur de signature, création répétée,
échec après écriture locale, et conflits d'identité.

## G : réparations Fedow et défaut de livraison

La surcharge crée un wallet pour un utilisateur existant qui n'en a plus ; elle
crée aussi une transaction FIRST de montant zéro si le journal d'une monnaie
est vide. FIRST est la première ligne de la chaîne de transactions de cet actif.
Ces ajouts ont été importés avec une ancienne copie complète du serializer : ils
écrasent aussi les protections de recharge ajoutées dans la référence récente.

Les défauts de recharge sous échec et concurrence ont été reproduits localement
sur PostgreSQL ; voir `2026-10-03-fork/INVESTIGATION.md`. Aucun incident de production
n'est déduit de ces tests.

Proposition prioritaire : repartir du serializer de la référence épinglée et
examiner séparément si ces deux réparations sont encore nécessaires. Mettre les
réparations d'état initial dans un bootstrap explicite et reprenable lorsqu'elles
sont justifiées, puis conserver l'atomicité et les contraintes upstream dans les
transactions ordinaires. Aucune correction de G n'est appliquée dans ce lot.

## H : suivi financier — proposition et risques

Le dashboard est une application Django, avec calculs ORM et rafraîchissement
JSON. Les fonctions examinées lisent les transactions et les tokens ; elles
n'écrivent pas les soldes. Elles peuvent néanmoins provoquer des erreurs HTTP,
charger la base et partager les ressources du processus Fedow avec les recharges.

Constats de code à corriger avant conservation durable :

- Les routes du suivi n'ont pas de garde de connexion/admin explicite dans les
  vues et URLconf audités. Aucun test d'accès public sur le serveur n'a été effectué.
- La liste des bars parcourt les métadonnées de toutes les ventes, et contient
  des libellés particuliers aux 100J. Certaines métadonnées sont décodées comme
  représentation textuelle Python ; ce n'est pas un contrat de données robuste.
- Le chiffre calculé `recharges - dépenses` sur une période ne constitue pas un
  solde réel : il ignore notamment un solde antérieur et les remboursements.
- Un filtre de lieu mal formé peut produire une erreur de validation non gérée.

Proposition : module `gala_dashboard` ajouté à l'image Fedow, routes spécifiques
ajoutées sans remplacer les vues/routes générales upstream, garde admin sur HTML
et JSON, filtre de lieu/période validé, agrégations bornées, cache court partagé
et erreur explicite en cas d'échec. Séparer visuellement flux de la période et
solde réel lu dans les tokens. Préserver les filtres par bar avec un contrat de
métadonnées défini ; isoler le décodage ancien pour les données historiques.
Le suivi n'effectue aucune réparation ni écriture monétaire.

Tests à faire : refus sans droits, totaux et solde réel sur un jeu avec solde
initial/recharge/vente/remboursement, filtres invalides, et requêtes sur un volume
représentatif. Un cache court réduit les requêtes répétées sans promettre une
isolation complète des ressources entre dashboard et écritures financières.

## I / L : configuration nécessaire, livraison à revoir

I est la configuration Django : moteur et connexion PostgreSQL, cache, domaines,
origines CSRF, templates, journaux et intégrations. Retirer seulement le fichier
Fedow ferait revenir SQLite dans sa référence. Une configuration erronée peut
empêcher le démarrage ou viser une autre base. Proposition : module de réglages
inclus dans l'image, valeurs variables et secrets lus depuis l'environnement,
avec contrôles de moteur/base attendus avant démarrage.

L est le routage Nginx : proxy Django, WebSockets, statiques/médias, sources et
alias `/admin` vers `/adminstaff/` pour LaBoutik. L'alias ajoute un chemin d'accès
et conserve l'authentification de la route cible ; ce n'est pas un mécanisme de
connexion. Une erreur de syntaxe peut empêcher Nginx de démarrer ; une cible
incorrecte peut provoquer des 502/404 ou casser les WebSockets.

Proposition : trois petites images Nginx avec leurs fichiers de configuration
(et substitutions de domaines via environnement si nécessaire). Vérifier
`nginx -t` dans un réseau de test avec les noms DNS attendus, puis les routes HTTP,
WebSockets, sources et alias admin avant changement de release. Aucune modification
de I/L ni retrait de leurs montages n'est exécuté à ce stade.

## Étapes soumises à examen

1. Valider cette architecture et les propositions D/E/H.
2. Préparer en priorité la correction G avec ses tests d'échec/concurrence.
3. Construire les images des personnalisations validées, puis migrer I/L sans
   changer les bases ni le mécanisme de secrets.
4. Vérifier la stack isolée et l'offre de sources avant toute promotion.

Aucun `git revert` global de l'import infrastructure, aucun accès à la production,
et aucune modification de soldes pendant ce lot.
