# Nouvelle architecture — TiBillet V2, Gala et Kfet

**Document de référence vivant — ouvert le 3 novembre 2026.**

Ce document rassemble les analyses réalisées dans le workspace Sydney, les contraintes exprimées et les questions restant à trancher. Il sera mis à jour dans ce même fichier au fil des échanges. Les propositions ne sont pas des fonctionnalités déjà livrées ni des autorisations de mise en production.

## 1. Statuts et règles de travail

- **Vérifié** : comportement lu dans la version du code étudiée ou observé sur la VM ; la preuve est précisée.
- **Confirmé par l'utilisateur** : contrainte ou règle explicitement exprimée.
- **Piste à étudier** : proposition discutée, sans décision d'implémentation ni déploiement.
- **À vérifier** : question non encore résolue ou parcours non validé de bout en bout.

**Règle confirmée :** toute modification de code, de script ou de configuration publique passe par le dépôt, un commit identifiable, les validations et la construction avant activation. Aucun patch de code manuel dans les conteneurs. Les secrets restent hors Git ; les modèles et noms de variables sont versionnés. L'étude actuelle ne déclenche pas de migration, de changement DNS ou de paiement.

L'utilisateur souhaite construire l'instance actuelle avec CAWL en test. Avant la production, il prévoit une copie de test isolée, puis les identifiants CAWL réels sur l'instance de production. Cette séparation reste à préparer ; elle n'a pas été effectuée.

## 2. Résumé des contraintes et pistes

| Sujet | Conclusion / état |
|---|---|
| Cartes imprimées | Adresse confirmée : `https://galas-am-aix.rezal.fr/qr/<identifiant>` |
| Réutilisation des cartes | Confirmée : les mêmes cartes doivent resservir entre éditions |
| Identités physiques | Conserver UUID QR, numéro imprimé et UID NFC ; ne pas régénérer ces associations |
| Kfet / Gala | Deux installations ou VM sont envisagées pour l'indépendance ; choix précis encore à arrêter |
| Éditions du gala | Décision confirmée : une installation commune et un lieu natif par édition, avec ses points de vente et sa billetterie ; pas encore mis en place |
| Alternative étudiée | Une refonte pour isoler les points de vente par événement a été comparée ; l'utilisateur a retenu la réutilisation des lieux |
| Domaines | Wildcard `*.galas-am-aix.rezal.fr` envisagé pour éviter une intervention Estia à chaque lieu |
| Adresse racine | Portail cashless commun demandé ; pas une reprise du contenu du site de communication ni une vitrine générique |
| Gestion interlieux | Compte central avec cartes, monnaies et accès au remboursement natif ; administration des éditions, rôles et lots |
| Profil des nouveaux lieux | Confirmé le 05/11 : fédération, monnaies/cashless et caisse actifs ; site personnalisé et autres modules optionnels désactivés. Valeurs dans `TiBillet/settings.py`, appliquées dans la création native ; aucune configuration JSON parallèle |
| Monnaie de chaque gala | Cible confirmée le 05/11 : une monnaie locale distincte par édition, commune aux recharges CAWL et au stand. « Offline » signifie ici rechargé au stand, pas caisse sans Internet. Aucun crédit partagé entre éditions |
| Gala live | Un seul accès utilisateur vers le gala explicitement désigné live ; les anciens soldes et accès au remboursement restent consultables |
| Remboursements | Mécanisme TiBillet conservé ; message annonçant sept jours après la date du gala, puis coupure manuelle par les organisateurs. Aucune demande en attente ni coupure automatique à ajouter |
| Cartes primaires | Gestion globale demandée, avec un réglage par carte autorisant ou refusant chaque lieu ; accès aux points de vente explicites |
| Authentification | Identité TiBillet commune et permissions natives ; rôles interlieux et passage entre domaines à développer |
| Production existante | Préserver le fonctionnement AWS et les adresses imprimées jusqu'à une bascule préparée |

La conception détaillée retenue pour poursuivre l'étude est dans [Portail interlieux des Galas](PORTAIL-INTERLIEUX-GALAS.md) : parcours, activation manuelle, permissions, accès au remboursement natif avec message des sept jours, lots, cartes primaires et ordre de réalisation. Les besoins sont confirmés ; les mécanismes supplémentaires proposés ne sont pas encore livrés.

## 3. Ce qui existe actuellement

Constats réalisés le 3 novembre 2026 sur la version VM `122d9d374f50b51141c4dc45fde77ffaac3f7ea1`. Treize fichiers structurants ont été comparés par SHA256 entre le dépôt étudié et la VM : identiques. Les inventaires de lieux ont été faits en lecture seule. Ces constats datés doivent être revérifiés avant une opération future.

| Adresse | Rôle actuel |
|---|---|
| `gala-test.rezal.fr` | Tenant technique `public`, accueil général TiBillet et assistant de création |
| `cashless.gala-test.rezal.fr` | Lieu nommé Lespass, schéma `lespass`, moteur V2 ; administration et caisse du même lieu |
| `fedow.gala-test.rezal.fr` | Service Fedow distant, pas un lieu métier supplémentaire |
| `galas-am-aix.rezal.fr` | Domaine imprimé des cartes ; DNS observé vers l'ancienne infrastructure AWS, distincte de la VM actuelle |

Le mot `cashless` n'impose pas un logiciel séparé : cette adresse dessert un lieu qui porte aussi sa billetterie, ses pages et son administration. La racine générique vient de l'association du domaine au tenant public ; ce n'est pas une obligation métier pour le collectif.

La base contient plusieurs lieux de démonstration et des emplacements en attente, mais pas deux organisations déjà distinctes nommées Kfet et Gala. Au relevé : Lespass contient 185 événements, 29 produits de caisse, trois stocks et sept points de vente. Ces objets ne sont pas autant d'installations. Le compte de l'utilisateur a reçu les droits admin du lieu Lespass ; il n'est pas superutilisateur global.

Le runtime est en `TEST=0`, `DEBUG=0`, `DEMO=0`, avec `CAWL_TEST=1`. Les vrais mails passent par Brevo ; un unique mail applicatif de validation a été reçu. Les tests capturent leurs mails dans Mailpit. Gunicorn, Daphne et le worker Celery existant sont utilisés, sans doublon de worker. Les WebSockets via Estia puis le domaine public ont été vérifiés avec un handshake 101 valide. Le contenu et le certificat de `hello.rezal.fr` sont restés identiques dans les contrôles avant/après.

Ces vérifications ne prouvent pas encore un parcours matériel caisse/NFC complet ni un paiement CAWL de test avec retour et webhook de bout en bout.

## 4. Vocabulaire : machine, installation, lieu, événement, point de vente

| Niveau | Sens | Exemple |
|---|---|---|
| Serveur / VM | Machine qui héberge les services | VM Gala ou VM Kfet |
| Installation / instance | Déploiement de TiBillet, sa configuration et ses services | Une pile avec sa base, ses workers et ses réglages CAWL |
| Lieu / tenant | Unité de gestion ; pas nécessairement un bâtiment | Kfet, Gala ou une édition de festival |
| Événement | Programmation appartenant à un lieu | Gala 2026, soirée de Noël |
| Point de vente | Comptoir ou usage de caisse dans le lieu | Bar, Restaurant, Cashless, Billetterie |
| Terminal | Appareil associé au lieu | Téléphone ou tablette de caisse |

Une installation peut héberger plusieurs lieux ; chaque lieu peut contenir plusieurs événements et points de vente ; plusieurs terminaux peuvent utiliser un même point de vente.

Décision confirmée pour les éditions Gala, **pas encore déployée** ; la séparation Kfet reste une proposition :

```text
Installation Gala
  Lieu Gala 2026 -> événement Gala 2026 -> plusieurs points de vente
  Lieu Gala 2027 -> événement Gala 2027 -> plusieurs points de vente
Installation Kfet
  Lieu Kfet -> plusieurs soirées / événements -> plusieurs points de vente
```

Deux installations ne nécessitent pas obligatoirement deux VM. Deux VM renforcent l'indépendance d'exploitation, mais un proxy ou d'autres services peuvent encore être communs.

## 5. Séparation réelle entre lieux

TiBillet utilise Django et `django-tenants` avec PostgreSQL. Un nom de domaine est associé à un `Customers.Client` par `Customers.Domain`. Le middleware sélectionne le schéma du lieu. Plusieurs schémas existent dans une base commune ; ce ne sont pas des serveurs indépendants.

**Données propres au lieu :** configuration de l'organisation, événements, réservations, billets, catalogue et tarifs, points de vente, terminaux, cartes primaires, inventaire, ventes, règlements, plan comptable, clôtures et réglages de modules. Les pages existent également dans chaque schéma.

**Données et services partagés dans l'installation :** registre des lieux/domaines, identités des utilisateurs, registre des cartes, portefeuilles, tables du moteur monétaire V2, application, workers, infrastructure, SMTP et réglages globaux du prestataire de paiement.

Les données monétaires partagées portent des références de lieu et de monnaie et sont filtrées par les services. Leur isolation ne repose pas sur un schéma différent par solde. Cette étude n'est pas un audit exhaustif des permissions ou une certification de sécurité/comptabilité.

Sources : [Customers](../../Customers/models.py), [réglages Django](../../TiBillet/settings.py), [services monétaires](../../fedow_core/services.py). Mécanisme : https://django-tenants.readthedocs.io/en/latest/ .

## 6. Plusieurs événements ou points de vente ne remplacent pas deux lieux

**Plusieurs événements :** oui, avec dates, jauges, réservations, billets et produits de billetterie distincts. Un lieu peut conserver plusieurs éditions. Un seul événement dans un lieu ne supprime aucune fonction de billetterie.

Mais créer un événement ne crée pas une nouvelle organisation, un nouveau catalogue indépendant, une monnaie cashless, une équipe admin ni une clôture distincte. Une vente ordinaire au bar n'est pas automatiquement rattachée à l'événement de billetterie du même jour : `Vente` porte notamment son point de vente, pas une relation universelle à `Event`.

**Plusieurs points de vente :** ils ont leurs sélections d'articles, moyens de paiement, droits opérateurs et ventilations de vente. Mais un même produit vendu au Bar et au Restaurant puise dans son stock commun. Le stock est un enregistrement par produit. Les clôtures couvrent le lieu entier, avec ventilation par point de vente.

Deux points de vente Kfet/Gala conviennent à une gestion commune. Deux lieux sont plus adaptés si l'on veut séparer administrateurs, catalogues, stocks, ventes et clôtures. Le besoin de deux installations est une question supplémentaire de configuration et d'exploitation.

Sources : [Event / LigneArticle](../../BaseBillet/models.py), [Vente](../../BaseBillet/models_vente.py), [points de vente et clôtures](../../laboutik/models.py), [stocks](../../inventaire/models.py), [clôtures comptables](../../comptabilite/models.py).

### 6.1. Proposition : donner aux événements la séparation des lieux

**Question de l'utilisateur, 03/11/2026 :** modifier TiBillet pour que les événements soient cloisonnés au même niveau que les lieux, dans une installation commune. C'est une piste d'architecture, pas une demande de migration immédiate.

Une seule installation peut déjà héberger tous les lieux. Le choix supplémentaire concerne l'unité de séparation des opérations et la navigation : une adresse commune ne suffit pas à choisir l'édition concernée par une recharge ou un remboursement.

**Constats du code actuel :** `Event` porte la programmation et la billetterie ; `Vente` référence son point de vente mais ne possède pas de relation universelle à un événement ; `Stock` est unique par produit ; les clôtures couvrent le lieu ; les monnaies V2 portent un `tenant_origin` et leurs transactions un `tenant` ; les permissions administratives sont notamment définies par lieu. Filtrer une liste par événement ne procurerait donc pas le cloisonnement d'un lieu.

Deux approches sont à comparer :

- **Conserver les unités existantes et unifier l'entrée.** Présenter un tenant comme un espace de gestion (Gala 2026, Gala 2027, Kfet), tout en conservant ses événements de billetterie. Un portail commun peut donner accès aux espaces autorisés et masquer la complexité des domaines. Le routage des sessions, des cartes et des opérations reste à concevoir ; cette interface n'existe pas encore dans les ajouts de la page d'accueil.
- **Ajouter un véritable périmètre d'exploitation sous un lieu.** Un lieu Gala pourrait contenir plusieurs éditions séparées. Il faudrait définir ce qui appartient à ce périmètre : ventes et règlements, produits et stocks, terminaux et droits, monnaies et remboursements, rapports et clôtures, tâches asynchrones, retours prestataires et WebSockets. Les événements natifs de billetterie pourraient lui être rattachés. Cela implique une évolution du modèle, des migrations et une vérification des autorisations, pas seulement un nouveau champ de filtrage.

La seconde approche doit aussi couvrir les activités permanentes (Kfet), les événements simultanés et les données historiques. Le choix d'un périmètre doit rester explicite et être validé côté serveur ; la dernière édition consultée ou la seule date du jour ne suffit pas pour attribuer une opération financière.

**Décision ultérieure de l'utilisateur :** conserver les lieux natifs, un par édition, dans une installation commune, et construire une entrée interlieux. La refonte par événement n'est donc pas l'option retenue. Décider séparément si les crédits restent propres à chaque édition ou sont utilisables entre éditions : une identité et une carte communes ne tranchent pas cette règle. Voir la [conception du portail](PORTAIL-INTERLIEUX-GALAS.md).

Sources complémentaires : [monnaies et transactions](../../fedow_core/models.py), [permissions](../../ApiBillet/permissions.py), [routage des domaines](../../Customers/models.py).

## 7. Navigation, administration et modules

L'administration commune regroupe les outils, tandis que l'interface de caisse sert aux opérations d'encaissement. Le bouton « Ouvrir la caisse » mène donc à la caisse et à l'identification du personnel par carte primaire ; il ne sert pas à modifier les articles.

Accès actuels du lieu Lespass :

- Gestion : `https://cashless.gala-test.rezal.fr/admin/`.
- Configuration caisse : `/admin/module/caisse/?onglet=configurer`.
- Articles : `/admin/BaseBillet/posproduct/`.
- Points de vente : `/admin/laboutik/pointdevente/`.
- Exploitation : `/laboutik/ouvrir/` puis `/laboutik/caisse/`.
- Compte personnel et accès aux lieux administrés : `/my_account/`, rubrique « Mes responsabilités ».

L'entrée du menu latéral « Caisse & Restaurant » est censée ouvrir le module de gestion. Le raccourci « Ouvrir la caisse » ouvre l'exploitation. Le signalement utilisateur d'un clic menant au NFC n'a pas établi quelle entrée était utilisée ; aucun correctif de navigation n'a été fait sur cette seule hypothèse.

| Ensemble de modules | Fonctions |
|---|---|
| Espace en ligne / Lespass | Site, agenda, billetterie, adhésions, réservations |
| LaBoutik | Produits, tarifs, points de vente, caisse, inventaire |
| Réseau / monnaies | Cartes, portefeuilles, monnaies et fédérations |
| Contributions | Financement participatif, budgets et bénévolat |
| Matériel | Terminaux, imprimantes, bornes et tireuses |
| Gestion transversale | Ventes, règlements, rapports et clôtures |

Présence dans les menus et activation d'un module ne prouvent pas tous ses parcours. Exemple : le type de caisse Advanced est indiqué comme réservé/non codé dans le modèle. Les bornes ont notamment des parcours Stripe Terminal : leur compatibilité CAWL complète n'a pas été validée. La newsletter prévoit Ghost et est désactivée sur le lieu actuel ; elle est distincte des mails transactionnels Brevo.

Sources : [navigation](../../Administration/admin/dashboard.py), [administration](../../Administration/admin/site.py), [modèles](../../BaseBillet/models.py).

## 8. Création native d'un lieu dans l'interface

Le bouton « Créer son espace » ouvre `/onboard/`. Le formulaire d'identité a été vérifié en HTTP 200 sur `https://gala-test.rezal.fr/onboard/`. Le parcours comporte identité/email, vérification si nécessaire, nom et adresse web du lieu, adresse géographique, présentation/logo, puis création asynchrone. Le compte créateur reçoit les droits d'administration du lieu.

**Point de fonctionnement vérifié dans le code :** valider « Continuer » à l'étape Présentation et logo déclenche déjà la création. L'étape de brouillons d'événements existe dans le code mais est sautée dans le flux courant ; les événements peuvent être créés ensuite.

La VM propose le suffixe `gala-test.rezal.fr` et avait vingt emplacements en attente au contrôle. Cela ne prouve pas que chacun est entièrement migré : le créateur vérifie ce point avant d'en sélectionner un.

L'assistant crée le lieu et son association Domain ; il n'ajoute pas à lui seul DNS public, certificat wildcard ou règles Estia/Traefik. Le routage actuel accepte seulement les adresses déjà configurées. Un nouveau lieu n'est pas automatiquement autorisé à utiliser CAWL.

Ne pas confondre ce parcours avec « Créer un nouveau lieu » dans l'assistant d'un événement : ce dernier peut désigner une adresse physique d'événement, pas une nouvelle organisation/tenant.

Sources : [routes](../../onboard/urls.py), [vues](../../onboard/views.py), [création du tenant](../../BaseBillet/validators.py), [tâches](../../onboard/tasks.py).

## 9. Portail du collectif et pages interlieux natives

L'utilisateur ne souhaite pas une vitrine publicitaire TiBillet comme entrée de ses services, ni remplacer le site de communication des Galas. Il demande une entrée cashless commune, avec compte personnel interlieux et administration autorisée. L’accueil et le compte interlieux sont désormais implémentés dans `seo/portal/` ; leur activation et leur validation réelle sont à vérifier séparément du code.

**Il existe déjà une page réseau publique native : `/federation/`.** La vue `FederationViewset` présente une carte et une liste du lieu courant et de ses lieux fédérés. Le titre peut être personnalisé (`federation_menu_name`), ainsi qu'un texte d'introduction, le tri et les filtres.

Les lieux affichés proviennent des liens explicites `FederatedPlace`, éventuellement des lieux entrants et d'abonnements par tags. Pour un portail limité au collectif, il faudra étudier la sélection explicite des lieux et les options d'élargissement, plutôt que supposer que tous les lieux actifs sont souhaités. Les mécanismes de fédération permettent aussi de faire remonter des événements dans un agenda commun.

Le `/explorer/` du tenant public présente le réseau général ; ce n'est pas automatiquement une sélection privée du collectif. `/my_account/` propose déjà « Mes responsabilités », avec les lieux administrés et leurs liens vers les back-offices. Ces accès ne constituent pas une gestion complète de toutes les organisations sur une seule page.

**Trois fonctions à distinguer pour le futur portail :** présentation publique du collectif, accès personnels/administratifs après connexion, et entrée permanente des cartes. Les réunir sur un même domaine ne doit pas fusionner les données, droits ou soldes des lieux.

La composition exacte de la racine et son articulation avec les pages réseau existantes restent à réaliser selon la [conception détaillée du portail](PORTAIL-INTERLIEUX-GALAS.md). L'accès à Explorer reste secondaire. Réutiliser l'existant avant d'ajouter une nouvelle interface est la règle retenue.

Sources : [FederationViewset](../../BaseBillet/views.py), [FederatedPlace / FederationConfiguration](../../BaseBillet/models.py), [page réseau V2](../../pages/templates/pages/V2/vues/reseau.html), [Mon compte](../../pages/templates/pages/V2/vues/compte/index.html), [routes publiques](../../TiBillet/urls_public.py).

## 10. Authentification et permissions interlieux

**Besoin désormais confirmé :** utiliser le login TiBillet sur le domaine racine et donner accès à une interface de gestion des lieux du collectif, en réutilisant les fonctions existantes et leurs permissions. La conception des nouveaux droits interlieux reste à implémenter.

Éléments déjà vérifiés :

- L'identité `TibilletUser` est partagée dans une installation.
- `client_admin` définit les lieux que la personne administre ; `is_staff` seul n'autorise pas tous les lieux.
- `TenantAdminPermissionWithRequest` vérifie notamment l'administration du lieu courant, le compte actif et son type humain ; un superutilisateur a une portée globale.
- `RootPermissionWithRequest` exige une authentification et le statut superutilisateur.
- Des droits distincts existent pour initier un paiement, créer des événements ou gérer des contributions.
- Les comptes de terminaux et leurs clés API sont distincts des administrateurs humains.
- Le compte personnel liste les lieux autorisés dans « Mes responsabilités ».
- La section « Root Configuration » de l'administration prévoit un accès à la liste des lieux pour les superutilisateurs ; le modèle Client possède notamment une action de passage vers leur administration. Sa portée exacte et son adéquation au rôle de responsable du collectif restent à analyser.
- Le domaine public n'expose actuellement pas un `/admin/` racine actif : sa route est commentée dans `urls_public.py`.
- Les cookies de session sont actuellement limités à l'hôte. Identité commune ne signifie donc pas connexion automatiquement conservée entre tous les sous-domaines.
- La liste native des lieux n'est pas un CRUD complet : création/suppression refusées dans cette page ; les champs du lieu sont en lecture seule et les superutilisateurs peuvent éditer les domaines via un inline.
- Il existe une action native de passage à l'administration d'un lieu pour superutilisateur. Elle ne constitue pas une délégation de ce pouvoir à tous les admins du collectif.
- Un SSO transitoire existe pour le parcours d'onboarding tenant vers racine : jeton signé, portée dédiée et durée courte. Son existence ne prouve pas un SSO général de portail vers tous les lieux. Il faut étudier le mécanisme dans son contexte avant de le réutiliser.

**Lecture pour le futur portail :** le login doit réutiliser les comptes TiBillet ; les fonctionnalités affichées doivent découler des droits natifs sur les lieux. Une personne administratrice de plusieurs lieux peut déjà être représentée par plusieurs associations `client_admin`. Cela ne nécessite pas automatiquement un superutilisateur global. Une interface de gestion interlieux limitée au collectif reste une piste à définir, pas une page complète déjà présente sur la racine actuelle.

À vérifier avant de proposer une interface : couverture exacte des rôles, gestion interlieux existante, mécanismes de passage de session entre domaines, accès au login depuis la racine, révocation et absence d'accès aux lieux non autorisés. Ne pas créer un second système d'identités ni accorder un superutilisateur global simplement pour contourner une navigation manquante.

Sources : [utilisateurs](../../AuthBillet/models.py), [permissions](../../ApiBillet/permissions.py), [site admin](../../Administration/admin/site.py), [liste des lieux](../../Administration/admin_tenant.py), [vues du compte](../../BaseBillet/views.py), [cookies](../../TiBillet/settings.py).

## 11. Téléphones, Discovery et personnel de caisse

Le Discovery V2 est intégré à TiBillet. L'administrateur déclare un terminal dans son lieu ; un PIN à six chiffres est généré. L'application appelle `/api/discovery/claim/` sur le serveur Discovery configuré. Le PIN désigne le lieu ; le téléphone reçoit son adresse et une clé API de terminal. Le PIN est à usage unique et sa durée de vie actuelle est d'une heure.

Le client Android V2 présent dans le dépôt permet de changer le serveur Discovery et utilise ensuite `/laboutik/auth/bridge/` pour ouvrir la caisse. La version réellement installée sur les téléphones n'a pas été inspectée : cette lecture de code ne prouve pas sa compatibilité.

Dans la configuration publique actuelle, le point d'entrée Discovery est exposé sur le domaine racine. L'appairage ne nécessite pas un service Discovery distinct pour chaque édition. Il faut toutefois des droits/appairages propres aux lieux ; la réutilisation d'un téléphone entre éditions, les profils enregistrés et la révocation sont à valider en réel.

Le terminal représente l'appareil ; la carte primaire identifie le personnel et ses points de vente autorisés. Le PIN d'appairage et le scan NFC d'un opérateur sont donc deux mécanismes différents.

Sources : [modèle Discovery](../../discovery/models.py), [claim](../../discovery/views.py), [services](../../discovery/services.py), [terminal](../../laboutik/models.py), [client Android V2](../../laboutik_client_android_v2/mobile-app/www/assets/js/modules/utils.js). Le README Discovery contient des descriptions anciennes ; le code actuel fait référence pour la création préalable du Terminal et les PIN expirables.

## 12. Cartes imprimées et réutilisation entre éditions

**Contraintes confirmées :** URL `https://galas-am-aix.rezal.fr/qr/<identifiant>` et cartes réutilisables. L'adresse imprimée doit rester pérenne, indépendamment des adresses de gestion des éditions.

Le parcours natif `/qr/<uuid>/` :

1. Valide l'UUID et retrouve la carte auprès du Fedow distant.
2. Lit le domaine du lieu d'origine de la carte.
3. Peut rediriger vers le domaine principal de ce lieu.
4. Propose la liaison à un compte ou la connexion du propriétaire.
5. Après identification, propose la recharge native du lieu si elle est activée.

Le QR imprimé ne prouve pas l'identité du porteur. Sans session, le scan d'une carte liée peut envoyer un mail au propriétaire. Aucun scan HTTP de carte réelle n'a été lancé pendant l'étude afin de ne pas déclencher un envoi non demandé.

**Une simple redirection vers la dernière édition n'est pas une solution déjà validée :** le routage natif vers l'origine peut la contredire ou produire une boucle. Le futur aiguillage doit préserver UUID, numéro imprimé et UID NFC, sans modifier silencieusement l'origine des cartes à chaque édition.

Piste adaptée : entrée QR permanente -> reconnaissance/authentification -> proposition du gala ouvert ou choix d'édition -> recharge native du lieu choisi. Les anciens soldes et remboursements gardent un accès explicite. Aucun code de cet aiguillage n'est encore livré.

La même carte peut porter des soldes de monnaies différents. Un `Token` correspond au couple portefeuille/monnaie. Créer un événement ne crée pas une monnaie et ne remet pas un ancien solde à zéro. Le parcours CAWL actuel sélectionne un produit de recharge TLF actif du lieu, pas une monnaie déterminée par un événement de billetterie.

Un changement de gala actif ne doit pas envoyer un paiement ou son webhook vers la mauvaise édition. Le lieu, la commande, le compte marchand et la monnaie à créditer doivent rester ceux du paiement initial, y compris pour les retours tardifs et remboursements.

Sources : [ScanQrCode](../../BaseBillet/views.py), [client Fedow](../../fedow_connect/fedow_api.py), [page carte liée](../../BaseBillet/templates/fonctionnel/qr_carte_liee.html), [modèles monétaires](../../fedow_core/models.py), [recharge CAWL](../../PaiementCawl/recharges.py), [sélection du produit](../../kiosk/credit.py), [tests QR](../../tests/pytest/test_qr_parcours_securise.py).

## 13. Stock physique, origines et migration

Le catalogue versionné décrit trois lots : 3 510 + 1 755 + 1 755 = **7 020 cartes**. Les documents d'exploitation décrivent des imports historiques sur AWS ; ce n'est pas une preuve d'import sur la nouvelle VM.

Relevé de la VM au 3 novembre : **158 cartes Fedow**, toutes de génération 1, origine renvoyant `cashless.gala-test.rezal.fr`. Le miroir Lespass ne contient que quatre cartes. Aucun Domain `galas-am-aix.rezal.fr` n'est enregistré dans Lespass de cette VM. Le stock complet du catalogue n'y est donc pas présent ; les fichiers privés des lots n'ont pas été comparés individuellement pendant cette étude.

Un importeur de déploiement existe : il pilote la commande native Fedow `import_cards`, conserve les associations identiques, ajoute les absentes et refuse les conflits. Son branchement au déploiement VM reste à préparer/vérifier. Il ne faut ni réinventer les identités ni publier les fichiers privés de cartes dans Git.

Importer le stock physique sur une base neuve ne transfère pas automatiquement les comptes, portefeuilles, soldes et transactions de l'ancien système. La reprise éventuelle de ces données sera un chantier distinct avec sauvegarde et contrôles, sans effacement implicite.

Sources : [catalogue](../card-stock.json), [procédure historique](operations/card-stock-import.md), [enveloppe native](../tools/runtime/import_card_stock_fedow.py), [tests d'import](../tests/test_card_stock.py).

## 14. Domaines, wildcard, certificat et Estia

**Piste discutée :** `*.galas-am-aix.rezal.fr` pour les lieux d'édition, avec conservation de `galas-am-aix.rezal.fr` pour le portail, Discovery et l'entrée QR selon le routage à définir. Les noms des lieux doivent rester sur un seul niveau, par exemple `gala-2027.galas-am-aix.rezal.fr`. La caisse intégrée reste sous `/laboutik/` ; inutile d'imposer `cashless.gala-2027...`.

Préparer une seule fois :

1. DNS wildcard vers l'entrée publique retenue, et enregistrement de la racine conservé explicitement.
2. Certificat couvrant la racine ET `*.galas-am-aix.rezal.fr`.
3. Routage Estia pour ce périmètre uniquement, en préservant le Host et les WebSockets.
4. Routage Traefik/nginx dans la VM, avec les exceptions des services fixes comme Fedow.
5. Paramètres d'hôtes/suffixes de TiBillet ; chaque lieu créé par l'interface conserve sa propre association Domain.

Objectif : une fois ces éléments validés, ne plus intervenir sur Estia pour chaque création de lieu. Le wildcard ne crée pas un lieu, ne donne pas de droits et n'autorise pas CAWL. Les noms inconnus ne doivent pas devenir des organisations accessibles par défaut.

Un certificat wildcard ne couvre qu'un niveau : il ne couvre ni la racine seule ni `cashless.gala-2027.galas-am-aix.rezal.fr`. Avec Let's Encrypt, les wildcard nécessitent DNS-01, à automatiser pour le renouvellement ; la validation HTTP actuelle ne suffit pas. L'accès au DNS et sa possibilité d'automatisation restent à étudier. Ne pas toucher aux autres certificats/services d'Estia pour cette préparation.

Au contrôle DNS : `galas-am-aix.rezal.fr` résout vers 51.44.90.200, et `gala-test.rezal.fr` vers 86.220.191.228. Un sous-domaine aléatoire sous le domaine de production n'a pas résolu. Ce constat ne remplace pas l'inventaire de la zone autoritaire et ne prouve pas l'état de tous les enregistrements. Aucune bascule DNS n'a été réalisée.

Sources : [configuration Estia](../estia/gala-test/nginx-https.conf.example), [routage VM](../estia/gala-test/compose.estia.yml), [association des domaines](../estia/gala-test/domaines.py). Références : https://letsencrypt.org/docs/challenge-types/#dns-01-challenge et https://www.rfc-editor.org/rfc/rfc9525.html#section-6.3 .

## 15. CAWL, monnaies et séparation test/production

Le connecteur de ce fork choisit le prestataire en ligne au niveau de l'installation (`PAYMENT_PROVIDER`). CAWL lit un seul jeu de paramètres marchands ; `CAWL_TEST` est global. `CAWL_TENANT_SCHEMAS` autorise explicitement les lieux qui peuvent encaisser. Sur la VM étudiée, la liste contient seulement `lespass` et CAWL est en test.

Deux lieux peuvent donc séparer leur gestion TiBillet tout en utilisant le même compte marchand. Cela ne crée pas deux comptes CAWL ni une ventilation bancaire automatique. Deux comptes marchands différents ou un lieu en test et l'autre en réel ne sont pas un simple choix par lieu dans cette implémentation.

La monnaie locale V2 vit dans `fedow_core` intégré à Lespass. Le service Fedow autonome (`fedow_django`, domaine `fedow.gala-test.rezal.fr`) est lui aussi hébergé sur la VM ; il reste utilisé notamment pour l'identité/origine des cartes et des fonctions du réseau. Ce n'est pas l'ancien service AWS : ne pas le supprimer ni modifier son rôle par confusion entre ces composants. Les soldes par monnaie peuvent être distincts et certaines monnaies peuvent être partagées explicitement via fédération. Partager une carte, un agenda et une monnaie sont trois décisions différentes.

Les vrais mails de connexion/confirmation et les paiements CAWL de test peuvent coexister. Les tests automatisés doivent continuer à capturer leurs mails. La copie future de test doit être isolée et configurée avant démarrage de ses workers/services ; ce document ne prescrit pas une simple duplication de VM avec toutes les connexions de production actives.

Sources : [CAWL / lieux autorisés](../../PaiementCawl/services.py), [configuration du SDK](../../payment_providers/cawl.py), [services monétaires](../../fedow_core/services.py), [isolation SMTP](../../TiBillet/mail_delivery.py), [runtime actuel](../estia/gala-test/README.md).

### 15.1. Audit de création et de cloisonnement des monnaies — 5 novembre 2026

**Décision confirmée :** une seule monnaie locale fiduciaire (TLF) par gala, avec un identifiant distinct pour chaque édition. Les recharges CAWL et les recharges au stand alimentent cette même monnaie. Le terme « offline » utilisé pendant l'échange désigne les recharges au stand ; il ne demande pas un fonctionnement de caisse sans connexion. La carte et l'identité sont réutilisables, les crédits ne passent pas d'une édition à l'autre.

**Vérifié dans le code :**

- La création native initialise le lieu, ses réglages, son administrateur et sa place/son portefeuille Fedow. L'activation des modules ne crée pas à elle seule une TLF locale. Le parcours Gala complète désormais cette étape avec le service natif V2.
- `Asset.tenant_origin` identifie le lieu émetteur ; un solde `Token` est propre au couple portefeuille/UUID de monnaie. Une nouvelle monnaie ne doit reprendre ni les jetons ni l'identifiant de l'ancienne édition.
- `AssetService.creer_asset` crée une monnaie locale. Le signal natif `creer_ou_mettre_a_jour_product_recharge` fabrique son produit de recharge et ses tarifs (1, 5, 10 et Libre). Ces mécanismes doivent être réutilisés dans le contexte du nouveau lieu.
- Le parcours CAWL sélectionne un produit de recharge dont la monnaie TLF appartient au lieu courant. La recharge au stand passe par `TransactionService.creer_recharge`, comme le crédit CAWL. Les origines des paiements sont conservées sans créer deux monnaies « online/offline ».
- Le remboursement CAWL existant calcule `min(solde de la monnaie, recharges CAWL de cette monnaie encore remboursables)`, dans le lieu courant. Avec une monnaie unique, ce plafond ne trace pas quels euros particuliers ont été dépensés en premier. Exemple : 20 € CAWL + 10 € au stand − 15 € dépensés = 15 € de solde et jusqu'à 15 € remboursables en ligne.
- La caisse choisit les monnaies locales accessibles : celles du lieu et celles explicitement partagées par une `fedow_core.Federation`. Elle peut aussi compléter un paiement avec le FED du réseau lu sur le service Fedow hébergé sur la VM. Une isolation stricte des galas ne doit pas simplement supposer ce solde FED nul.
- Le module public « Fédération / agenda » et le partage monétaire sont des mécanismes distincts. Le premier peut rester actif sans partager les crédits entre éditions.
- Plusieurs monnaies TLF peuvent actuellement être créées pour un même lieu. La recharge en ligne et la cascade de caisse choisissent chacune une première monnaie/produit selon leur ordre : il faudra éviter une sélection ambiguë pour un gala.

**Relevé en lecture seule sur la VM :** quatre monnaies locales existent, toutes rattachées au lieu `lespass` : Monnaie locale (TLF), Cadeau (TNF), Temps (TIM), Points fidélité (FID). Aucune `fedow_core.Federation` n'est configurée. Ce constat ne mesure ni les fonds FED du service autonome ni les soldes des personnes. Aucune monnaie ni aucun paiement n'a été créé ou modifié pendant l'audit.

**Adaptation et critères de validation :**

1. Initialiser une seule TLF propre au nouveau gala, via les services/signaux natifs ; laisser les monnaies et soldes existants intacts. Prévoir le rejeu et les créations interrompues sans doublon ni réinitialisation.
2. Garantir une sélection non ambiguë de cette monnaie pour la recharge CAWL et au stand. Ne créer ni cadeau, points, temps ou FED commun par défaut pour une nouvelle édition.
3. Limiter les dépenses du gala à ses monnaies autorisées ; vérifier aussi les chemins de complément, deux cartes et FED du service autonome, sans modifier le fonctionnement des installations hors Gala.
4. Tester deux galas simultanément actifs avec le même compte et la même carte : un solde dans A ne doit pas permettre un paiement dans B ; la recharge de B ne doit créditer que B.
5. Vérifier les plafonds et remboursements séparément par édition, ainsi qu'un retour/webhook CAWL tardif après changement du gala live : le paiement doit rester attaché à sa monnaie et son lieu d'origine.

**Implémentation :** `GalaEdition.currency_isolated` et `currency` rattachent explicitement chaque nouvelle édition à sa seule TLF. La migration additive `seo.0008` laisse les éditions existantes à `False` / `NULL` et ne touche à aucune monnaie ni aucun solde. Le parcours natif réserve un emplacement V2 vide sous verrou, inscrit l'édition, puis utilise `AssetService.creer_asset` dans le contexte de ce lieu. Le signal natif crée le produit et ses quatre tarifs. Une initialisation monétaire interrompue peut être reprise sans recréer de monnaie.

La sélection des monnaies, les recharges, les dépenses et les remboursements au stand sont limités à cette TLF **uniquement pour les nouvelles éditions explicitement cloisonnées**. Les fonds du réseau ne servent pas de complément dans ces éditions, et un remboursement ne clôture pas la carte réutilisable. Une édition sans monnaie prête ne peut pas devenir le gala live. Le service Fedow de la VM continue d'assurer ses rôles natifs ; les lieux existants ne sont pas convertis.

**Validation :** les scénarios automatisés couvrent deux éditions actives avec une carte commune, les recharges CAWL et au stand dans une même TLF, le plafond natif de remboursement, la reprise sans doublon et le rejet d'une autre monnaie avant tout mouvement. Le 5 novembre 2026, les 35 tests du portail et de son intégration passent dans un conteneur séparé avec une base PostgreSQL de test dédiée ; la vérification des migrations ne détecte aucun écart. Les prestataires sont simulés et aucun paiement, remboursement ou mail réel n’est effectué. Une sauvegarde privée de la VM est vérifiée avant déploiement, avec des empreintes des monnaies, jetons, transactions, modules et rattachements Fedow existants.

Sources : [création native](../../BaseBillet/validators.py), [modèles et fédérations monétaires](../../fedow_core/models.py), [services monétaires](../../fedow_core/services.py), [produits de recharge automatiques](../../fedow_core/signals.py), [choix du produit CAWL](../../kiosk/credit.py), [recharge CAWL](../../PaiementCawl/recharges.py), [plafond de remboursement](../../PaiementCawl/remboursements.py), [soldes et cascade de caisse](../../laboutik/views.py).

## 16. Comparaison des architectures discutées

| Choix | Séparation obtenue | Ce qui reste commun |
|---|---|---|
| Un lieu, plusieurs événements | Programmation, billets, réservations et jauges | Organisation, catalogue, stocks par produit, monnaies configurées et clôtures |
| Un lieu, plusieurs points de vente | Écrans/articles proposés, droits opérateurs et ventilation | Gestion du lieu, stocks des produits communs et clôtures |
| Plusieurs lieux, une installation | Réglages, catalogues, stocks, admins, ventes/clôtures et monnaies configurées | Application, infrastructure, identités/cartes et paramètres CAWL globaux |
| Plusieurs installations | Bases, paramètres marchands et déploiements configurés séparément | Éventuellement machine/proxy et services externes volontairement partagés |

L'utilisateur a retenu une installation commune aux éditions Gala et un lieu par édition. Le choix d'une installation Kfet indépendante reste à arrêter séparément. La contrainte des cartes réutilisables impose l'entrée QR stable et l'accès aux anciennes monnaies/remboursements, même lorsqu'un nouveau gala est live. Cette décision n'est pas encore déployée.

## 17. Questions ouvertes et prochaines analyses

Priorités :

1. **Socle du portail / permissions :** registre des éditions, sélection explicite du seul gala live, droits collectifs et passage de session ; réutiliser le login TiBillet.
2. **Compte personnel central :** cartes associées, soldes par monnaie sans double comptage, anciennes éditions et accès au gala live.
3. **Remboursements simplifiés :** conserver les routes et règles natives ; afficher sept jours après la date du gala. Les organisateurs laissent la monnaie active puis la désactivent eux-mêmes. Aucun dossier en attente, échéance bloquante ou nouveau traitement des non-réclamés à développer.
4. **Domaines :** étudier zone DNS, wildcard, DNS-01, renouvellement et routage Estia/VM, sans basculer le domaine imprimé pendant le développement.
5. **Cartes et rôles :** inventaire des lots réellement chargés, autorisations par carte primaire et par lieu, droits admins cohérents entre lieux ; préparation de l'import et reprise des données à décider séparément.
6. **Validation réelle :** téléphone V2 appairé, carte physique, deux lieux/éditions de test, recharge CAWL test, retour et webhook dans le bon contexte.
7. **Production :** préparer la copie de test isolée puis une bascule contrôlée ; préserver AWS tant que la nouvelle chaîne n'est pas validée.

## 18. Profil des nouveaux lieux — décision du 5 novembre 2026

**Confirmé par l'utilisateur :** chaque nouvelle édition doit commencer avec les modules fédération, monnaies/cashless et caisse activés. Le module « Site web personnalisé » doit être désactivé. La connexion native de Lespass reste disponible : ce module ne constitue pas un autre système de connexion.

| Réglage initial | Valeur retenue |
|---|---|
| Fédération (`module_federation`) | Activé |
| Monnaies et cashless (`module_monnaie_locale`) | Activé |
| Caisse (`module_caisse`) | Activé |
| Site personnalisé (`module_pages`) | Désactivé |
| Billetterie, adhésions, financement participatif | Désactivés au démarrage ; activation ultérieure possible |
| Ressources, bénévolat, tireuses, kiosque, newsletter | Désactivés au démarrage |
| Inventaire | Disponible avec la caisse ; ce n'est plus un interrupteur autonome du tableau de bord |
| Nouveaux points de vente de caisse | Service direct (`service_direct=True`), sans gestion des commandes de table (`accepte_commandes=False`) |

**Correction de méthode demandée par l'utilisateur :** rechercher et réutiliser la configuration native avant toute adaptation. L'essai d'un fichier JSON séparé et de son chargeur a été abandonné et retiré avant publication ou déploiement.

**Mécanismes existants vérifiés :** `TiBillet/settings.py` contient les réglages de l'installation et le drapeau Gala. `BaseBillet.models.Configuration` contient les modules natifs par lieu et leurs valeurs initiales. `TenantCreateValidator.create_tenant` dans `BaseBillet/validators.py` consomme un emplacement préparé, obtient sa configuration native et la sauvegarde. `RootConfiguration` contient d'autres réglages communs (prestataires, intégrations), mais pas de profil de modules pour les nouveaux lieux. Aucun profil natif de modules prêt à l'emploi n'a été trouvé dans un fichier séparé.

**Adaptation native :** le dictionnaire `GALA_NEW_VENUE_MODULES`, dans `TiBillet/settings.py`, porte les valeurs initiales. `TenantCreateValidator.create_tenant` les copie dans les champs natifs juste avant sa sauvegarde habituelle, uniquement lorsque `GALA_CASHLESS_PORTAL=1`. Ce code ne s'exécute ni au démarrage ni à chaque déploiement. Le garde natif refuse de recréer un lieu déjà lié au brouillon ; les réglages des lieux existants et les changements ultérieurs des administrateurs restent conservés. Les autres installations gardent leur initialisation habituelle. Un nouveau lieu Gala prend un emplacement en moteur V2, sans convertir un emplacement legacy.

La création réutilisant des emplacements préparés, changer seulement les valeurs `default` du modèle ne garantit pas leur configuration. Les points de vente possèdent déjà les valeurs natives `service_direct=True` et `accepte_commandes=False` ; aucune nouvelle gestion des réglages restaurant n'est ajoutée. Les interrupteurs Ressources/Bénévolat pilotent surtout les menus : une fermeture effective des services demandera aussi de vérifier les routes.

Les mails transactionnels de connexion/confirmation restent actifs indépendamment de la newsletter. Les réglages d'envoi des rapports comptables sont distincts ; aucune préférence de désactivation n'a encore été confirmée pour ces rapports. « Fédération » activée ne décide pas à elle seule de partager les monnaies ou les soldes entre éditions.

**État :** l'adaptation native est implémentée dans le dépôt, sans nouveau fichier de configuration ni chargeur. Aucun lieu existant n'est reconfiguré par ce changement. La création réelle d'une nouvelle édition (domaine, certificat, monnaie, autorisation CAWL et matériel) reste un contrôle opérationnel distinct.

Sources : [réglages de l'installation](../../TiBillet/settings.py), [création native](../../BaseBillet/validators.py), [tâche de création](../../onboard/tasks.py), [configuration du lieu](../../BaseBillet/models.py), [points de vente](../../laboutik/models.py), [modules et inventaire](../../Administration/admin/dashboard.py).

## 19. Historique et maintenance du document

| Date | Analyse / évolution |
|---|---|
| 03/11/2026 | Analyse de la séparation installation/lieu/événement/point de vente et inventaire VM |
| 03/11/2026 | Étude de la création native de lieux et du routage des nouveaux domaines |
| 03/11/2026 | Contrainte confirmée : cartes imprimées sur galas-am-aix.rezal.fr, réutilisables entre éditions |
| 03/11/2026 | Lecture du parcours QR natif et constat du stock incomplet sur la VM |
| 03/11/2026 | Étude wildcard Estia/DNS/TLS et appairage Discovery V2 |
| 03/11/2026 | Ajout des pistes portail collectif, pages interlieux et permissions ; approfondissement en cours |
| 03/11/2026 | Comparaison d'un cloisonnement par événement avec la réutilisation des tenants derrière une entrée commune ; aucune refonte activée |
| 03/11/2026 | Choix confirmé : une installation commune aux éditions Gala, un lieu par édition, portail personnel et administration interlieux |
| 03/11/2026 | Délai confirmé : demandes pendant les sept jours suivant la clôture du gala ; étude des incompatibilités actuelles CAWL, des non-réclamés et des droits multi-lieux |
| 03/11/2026 | Demande explicite d'un réglage global par carte primaire pour autoriser ou refuser les lieux ; conception détaillée ajoutée dans PORTAIL-INTERLIEUX-GALAS.md |
| 03/11/2026 | Simplification demandée : remboursement interne conservé, message des sept jours après la date du gala et coupure manuelle ; l'ancienne proposition de demandes en attente et d'expiration automatique est abandonnée |
| 05/11/2026 | Profil des nouveaux lieux confirmé. À la demande de l'utilisateur, abandon du fichier JSON parallèle avant déploiement ; recherche de la configuration et de la création natives pour une adaptation minimale |
| 05/11/2026 | Adaptation native autorisée : valeurs initiales dans `TiBillet/settings.py`, copiées dans `Configuration` par la création habituelle, uniquement pour les nouveaux lieux de l'installation Gala |
| 05/11/2026 | Audit monétaire : une TLF propre à chaque gala, commune aux recharges CAWL et au stand ; création automatique absente et chemins de partage/FED à traiter pour garantir le cloisonnement |

**Maintenance :** enrichir ce fichier après chaque nouvelle analyse ; dater les constats de VM, noter les décisions explicites et garder visibles les questions non résolues. Un changement de proposition doit mettre à jour la synthèse, pas seulement ajouter une note contradictoire en bas. Ne pas y consigner de secrets, identifiants complets de cartes ou liens de connexion contenant des jetons.

Les anciens documents décrivent des architectures AWS/V1 et des décisions historiques : [architecture des galas](ARCHITECTURE-GALAS.md), [compatibilité CAWL/V2](COMPATIBILITE-CAWL-VERSION-INTEGREE.md), [ancien gala actif](operations/active-gala-and-shared-integrations.md). Ils restent utiles pour la reprise, mais ne doivent pas être lus comme le déploiement V2 actuel ou comme des décisions déjà reconfirmées pour la nouvelle cible.
