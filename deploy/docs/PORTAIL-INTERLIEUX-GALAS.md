# Portail interlieux des Galas — conception

**Étude du 3 novembre 2026.** Les exigences ci-dessous ont été exprimées par l'utilisateur ; les choix techniques proposés restent à implémenter et à tester. Aucun lieu, compte, droit, solde, remboursement ou domaine n'a été modifié pour cette étude.

Les constats de code portent sur le worktree `tibillet-local-upstream`, base `7f1ddb08`, avec l'adaptation d'accueil locale encore non publiée. Aucun nouvel inventaire de VM n'a été effectué pendant cette étude ; les chiffres historiques ci-dessous sont explicitement datés.

Document d'ensemble : [Nouvelle architecture](NOUVELLE-ARCHITECTURE.md).

## 1. Décisions confirmées et périmètre

- Une installation TiBillet commune aux éditions du gala, avec **un lieu natif par édition**. Chaque lieu conserve ses points de vente, catalogue, stocks, ventes et clôtures. Il peut contenir un ou plusieurs événements de billetterie.
- Le domaine principal devient une entrée de services cashless, pas une reprise du site de communication des Galas. L'ancien site sert uniquement de référence visuelle. La billetterie pourra être proposée ultérieurement.
- Les cartes physiques sont réutilisables. Leur adresse imprimée reste `https://galas-am-aix.rezal.fr/qr/<identifiant>` ; préserver UUID QR, numéro et UID NFC.
- Un espace personnel central présente les cartes associées au compte, les monnaies et soldes des différentes éditions, l'accès au remboursement natif de chaque lieu et un accès au seul gala actuellement live.
- Un espace d'administration interlieux permet de créer les lieux avec le parcours natif, les désactiver, gérer les administrateurs, consulter les lots de cartes et attribuer des cartes primaires réutilisables. L'utilisateur a précisé que chaque carte doit avoir un réglage global autorisant ou refusant explicitement les lieux.
- **Décision simplifiée qui remplace la première conception :** garder le mécanisme interne de remboursement TiBillet. Afficher que les participants disposent de sept jours après la date du gala pour demander leur remboursement ; les organisateurs attendent ce délai puis désactivent eux-mêmes la monnaie. Aucun dossier de demande, file d'attente, validation administrative supplémentaire ni coupure automatique à développer.
- La production AWS et les adresses imprimées ne basculent pas pendant la conception. CAWL reste en mode test dans l'instance en construction.

Ce choix concerne les éditions Gala. Le regroupement ou non de la Kfet dans cette installation reste à décider séparément ; il ne découle pas de l'accord sur les éditions.

## 2. Parcours utilisateur proposé

```text
Domaine commun → connexion TiBillet → Mon espace
  ├── Ma carte / mes cartes associées
  ├── Mes monnaies et soldes, classés par édition
  ├── Remboursement natif dans le lieu concerné + message sur les sept jours
  └── Accéder au gala en cours (un seul, s'il existe)

Compte autorisé → Administration du collectif
  ├── Éditions : créer, préparer, sélectionner comme live, désactiver manuellement
  ├── Administrateurs et périmètres de droits
  ├── Lots de cartes : catalogue, import et rapprochement
  └── Cartes primaires et accès accordés par lieu
```

Les intitulés et URL sont des propositions. Il n'y a pas de sélection automatique d'une édition à partir de la dernière page consultée, de l'origine historique de la carte ou de la seule date du jour.

Le bouton utilisateur mène à l'espace natif du gala live. Pour une personne autorisée à l'administration de ce gala, un accès à son back-office peut être proposé en plus. Ce bouton ne donne aucun droit par lui-même. Les opérations d'un ancien gala restent accessibles depuis ses lignes de solde/remboursement, sans proposer son accueil comme gala en cours.

## 3. Ce que le code fournit déjà

| Besoin | Mécanisme constaté | Limite actuelle |
|---|---|---|
| Identité commune | `AuthBillet.TibilletUser`, authentification TiBillet | Les sessions sont propres à chaque hôte ; le compte du lieu n'est pas une page de compte racine |
| Cartes et portefeuille | `CarteCashless`, association au compte, `Wallet`, moteurs Fedow | Le Fedow distant reste source de vérité pour certaines identités de cartes ; ne pas fusionner ses réponses avec les soldes locaux sans règle explicite |
| Soldes de toutes les monnaies V2 | `WalletService.obtenir_tous_les_soldes(wallet)` | Construire la présentation interlieux, les états d'éligibilité et le contrôle de propriété du portefeuille |
| Admin de lieu | `client_admin`, `is_tenant_admin`, `TenantAdminPermission` | Un admin de lieu n'est pas automatiquement gestionnaire du collectif |
| Création d'un lieu | Assistant natif `/onboard/` | Ajouter le rattachement au collectif et les étapes de préparation Gala ; le parcours crée effectivement un lieu et peut envoyer des mails |
| Attribution d'un admin de lieu | Action `SpecialAdminAction.toggle_user_right`, `set_staff` | Le parcours central, la délégation globale et la cohérence multi-lieux demandent une adaptation |
| Cartes et générations | `QrcodeCashless.Detail` et `CarteCashless` ; catalogue distant | La présence d'un catalogue ne prouve pas que toutes ses cartes sont chargées et utilisables |
| Carte primaire | `laboutik.CartePrimaire`, autorisations par point de vente | Enregistrement par schéma ; formulaire limité aux cartes d'origine du lieu, avec déclaration au Fedow distant |
| Remboursement CAWL | `PaiementCawl.remboursements`, suivi `CawlRefund`, écritures de vente/règlement | Comportement à conserver : la monnaie doit rester active jusqu'à la coupure manuelle par les organisateurs |
| Clôtures de caisse | `comptabilite.ClotureCaisse` | Rapports périodiques du lieu, pas le cycle de vie métier de l'édition |

La nouvelle interface doit composer ces services, sans dupliquer les identités, les soldes ni le moteur d'encaissement.

## 4. Soldes : une ligne par monnaie, pas une somme trompeuse

Le portefeuille appartient à la personne ; sa carte sert à l'identifier. L'espace présente donc les soldes du portefeuille du compte connecté et les cartes qui y sont réellement associées. Une carte anonyme non associée ne doit pas être rattachée sur la seule connaissance de son numéro.

Pour chaque monnaie : nom, édition émettrice, montant, unité, état et accès au remboursement lorsqu'il est permis nativement. Le message des sept jours et sa date de référence sont informatifs. Séparer les crédits en euros, cadeaux et points. Ne pas présenter un total mélangeant ces unités, ni additionner deux fois une monnaie acceptée dans plusieurs lieux. Pour une monnaie partagée, afficher une seule position et ses lieux d'acceptation.

Les anciennes monnaies doivent rester visibles dans l'historique, même lorsque leur usage ou leur remboursement est fermé. Après désactivation manuelle, leur solde n'est plus présenté comme disponible. Ne pas créer un traitement automatique des « non réclamés », ni effacer les données historiques.

Dans la VM V2, les soldes locaux viennent de `fedow_core`. La migration d'anciennes données AWS et leur rapprochement avec le Fedow distant restent un chantier distinct ; les afficher côte à côte ne prouve pas qu'ils sont indépendants ni additionnables.

La conception proposée conserve une monnaie propre à chaque édition et ses réglages natifs. Un partage de crédit entre éditions reste une décision supplémentaire. Réutiliser une carte ne transfère pas automatiquement ses anciens crédits.

## 5. Gala live et désactivation manuelle

La configuration commune désigne explicitement **zéro ou un** lieu live. Aucun choix par `first()`, par événement le plus récent ou par cache ancien. Un lieu de démonstration ou en préparation ne devient pas live implicitement. Si aucun gala n'est live, le compte reste accessible et le bouton indique l'absence de gala en cours.

Le choix du gala affiché et l'activation de sa monnaie sont deux réglages distincts. Une ancienne édition peut rester accessible pour le remboursement natif même lorsqu'une autre édition est désignée live, tant que les organisateurs n'ont pas désactivé sa monnaie.

Les organisateurs attendent sept jours après la date du gala, puis utilisent le réglage natif pour désactiver la monnaie. Conserver cette action manuelle. Aucun calcul d'échéance bloquant, timer de fermeture, champ `refund_deadline_at` ou nouveau cycle de demandes n'est requis.

**Désactiver ne signifie pas supprimer.** Conserver les lieux, soldes et écritures historiques. Les clôtures journalières de caisse restent les rapports natifs ; elles ne déclenchent pas une fermeture automatique des remboursements. Ne pas utiliser les commandes de suppression des lieux inactifs pour cette fonctionnalité.

## 6. Remboursement natif et message d'information

**La simplification demandée remplace la conception initiale de demandes en attente.** Le participant utilise directement le remboursement natif du lieu concerné. Le portail fournit l'accès au bon lieu depuis la ligne de monnaie, y compris pour une ancienne édition ; il ne crée aucun dossier à faire approuver et ne réserve aucun montant dans une nouvelle file.

Message prévu dans l'espace personnel et près de l'accès au remboursement :

> Vous disposez de 7 jours après la date du gala pour demander le remboursement de votre solde.

Afficher la date du gala concerné pour éviter l'ambiguïté entre éditions. Cette information ne bloque pas automatiquement l'action à J+7 : la coupure est effectuée par les organisateurs. Ne pas ouvrir artificiellement une nouvelle fenêtre de remboursement à partir d'une clôture de caisse.

Conserver les règles d'éligibilité existantes. Le code CAWL actuel limite le remboursement en ligne au minimum entre le solde de la monnaie et les recharges CAWL de cette personne encore remboursables, vers les paiements d'origine. Le portail ne transforme pas les autres crédits en recharges CAWL remboursables et n'ajoute pas de traitement administratif alternatif.

Conserver également les contrôles, écritures et états prestataire déjà fournis par TiBillet. La nouvelle interface n'ajoute ni statut métier « demande en attente », ni approbation, ni service financier parallèle. Désactiver/archiver la monnaie bloque déjà son remboursement dans ce fork : ce comportement est maintenant celui que l'utilisateur souhaite conserver, avec la coupure manuelle après le délai annoncé.

Le passage à « non réclamé » ne donne lieu à aucun nouveau traitement comptable automatique dans ce périmètre. L'ancienne proposition de réservations, d'expiration automatique et de traitement des demandes après échéance est abandonnée.

## 7. Authentification, droits et nouveaux administrateurs

Un seul compte TiBillet et son mécanisme d'authentification. Le domaine public ne monte pas actuellement l'espace natif `/my_account/` : il faut développer l'espace central en réutilisant les services appropriés, plutôt que monter tout le back-office d'un lieu sur le schéma public.

Proposition de rôles :

| Rôle | Périmètre |
|---|---|
| Participant | Ses propres cartes et soldes, accès au remboursement natif ; accès public au gala live |
| Administrateur d'une édition | Droits natifs `client_admin` sur les lieux autorisés ; pas de création de lieux ou d'admins globaux implicite |
| Gestionnaire du collectif | Permissions explicites sur les éditions du collectif, sa configuration, les lots, les cartes opérateurs et la délégation des droits |
| Superutilisateur technique | Pouvoir global existant, distinct du rôle courant des organisateurs |

Le rôle collectif proposé s'appuie sur les groupes et permissions Django/TiBillet, avec des permissions complémentaires pour les nouvelles actions. Ce n'est pas un second système de comptes. Être `is_staff` ou administrateur d'un lieu ne doit pas suffire à accéder à tous les lieux ou aux soldes de tous les participants.

L'ajout d'un administrateur passe par la recherche/invitation d'une personne et le choix explicite du périmètre : édition(s), ou collectif si le délégant possède ce pouvoir. Les droits d'édition utilisent les associations et services natifs. Les droits sur les futures éditions doivent être une politique explicite du rôle collectif, pas une propagation cachée des droits locaux.

**Point de code à corriger avant réutilisation multi-lieux :** la route actuelle `toggle_user_right?action=client_admin` retire `is_staff` global lors du retrait d'un seul lieu ; l'ajout n'effectue pas tous les traitements de `set_staff`. Il faut un service cohérent d'attribution/révocation réutilisé par l'ancienne route et le portail, avec tests pour une personne qui administre plusieurs lieux. La route est une bascule, donc impropre telle quelle aux reprises automatiques sans action explicite ajouter/retirer.

Chaque mutation vérifie la permission et le périmètre côté serveur, puis journalise qui l'a demandée et son résultat. Protéger la gestion des rôles contre l'élévation de privilèges et prévoir la conservation d'au moins un gestionnaire autorisé du collectif.

Les sessions restent limitées à l'hôte. Le passage portail → lieu doit réutiliser ou adapter un échange signé de courte durée, à usage unique et limité au destinataire, avec vérification des droits à l'arrivée. Le mécanisme SSO d'onboarding est une base à étudier, pas une preuve de SSO général déjà livré. Ne pas élargir globalement le cookie à tous les sous-domaines pour contourner ce travail.

## 8. Création et préparation d'une édition

Réutiliser les formulaires et services de `/onboard/`, avec une entrée administrative qui rattache le nouveau lieu au collectif et le laisse en préparation. La création depuis ce parcours doit vérifier les droits ; masquer seulement le lien public ne protège pas la route.

Le lieu créé doit être préparé avant activation : domaine, routage et certificat, monnaie locale, produit/tarif de recharge, droits, catalogue/points de vente et compatibilité des terminaux. Les modèles de catalogue peuvent faciliter la préparation, sans recopier ventes, soldes, clés d'API de terminaux ou remboursements d'une ancienne édition.

**Limite actuelle spécifique :** CAWL est global à l'installation et `CAWL_TENANT_SCHEMAS` n'autorise actuellement que `lespass`. Un nouveau lieu créé par l'assistant n'est donc pas automatiquement autorisé à encaisser. La procédure de préparation doit intégrer cette autorisation et les contrôles marchands avant d'afficher « prêt ». Même vigilance pour les domaines : le wildcard et son renouvellement ne sont pas encore activés.

Les formulaires natifs restent la source du parcours de création. Les extensions sont ciblées sur le rattachement au collectif, les droits et la préparation, sans reproduire le wizard dans un nouveau formulaire indépendant.

## 9. Lots de cartes et cartes primaires communes

### Inventaire

Afficher les lots/générations avec provenance, nombre attendu quand connu, nombre déclaré chez Fedow, nombre de miroirs locaux et rapprochement effectué. Les statuts proposés sont « catalogue connu », « import incomplet », « chargé et vérifié » et « anomalie ».

Il peut y avoir plusieurs lots chargés simultanément. Distinguer un éventuel lot actuellement distribué du registre de toutes les cartes valides : sélectionner un lot ne doit pas invalider les cartes des anciens lots. Les cartes déjà distribuées restent réutilisables, sous réserve de leur propre statut.

Le relevé de VM antérieur à cette étude avait constaté un catalogue de trois lots totalisant 7 020 cartes, mais seulement 158 cartes au Fedow distant de test et quatre miroirs locaux. Ces chiffres sont des constats datés, pas une preuve de l'inventaire courant ni un ordre d'import. Un miroir local peut être créé à la demande ; son absence seule ne prouve pas qu'une carte manque chez Fedow.

### Cartes opérateurs

Objectif : une même carte physique réutilisable d'une édition à l'autre, avec une gestion centrale de ses autorisations. Garder un registre commun d'autorisation opérateur qui référence la carte existante, puis attribuer ses accès aux lieux et points de vente choisis par les mécanismes locaux de `CartePrimaire`.

**Interface demandée :** une fiche par carte primaire, retrouvable par son numéro imprimé, avec une ligne par lieu. Chaque ligne propose « autorisé / interdit », les points de vente accessibles et le mode édition le cas échéant. Afficher l'état de synchronisation et les erreurs ; une autorisation en attente de validation n'est pas affichée comme opérationnelle. Prévoir aussi la révocation globale d'une carte perdue. Le réglage interlieux ne transforme pas son titulaire en administrateur humain.

Proposition par défaut : un lieu nouvellement créé n'accorde aucun accès à une carte existante. Le gestionnaire choisit les cartes et points de vente à autoriser avant l'ouverture. Une éventuelle action groupée reste une sélection explicite avec aperçu, pas une permission « tous les lieux futurs » implicite.

Le modèle `CartePrimaire` vit dans chaque schéma ; sa relation un-à-un à la carte est donc locale au lieu. Cependant, le formulaire actuel refuse une carte dont `detail.origine` est un autre lieu. Il faut adapter ce contrôle pour accepter une autorisation interlieux explicite, sans supprimer globalement les vérifications d'origine ou de périmètre, et réconcilier la déclaration auprès du Fedow distant.

Ne pas modifier l'origine de la carte pour la faire passer dans un nouveau lieu, ni générer une nouvelle carte à chaque édition. Les droits sur les points de vente ne sont pas déduits des noms « Bar » ou « Restaurant » : ce sont des objets différents dans chaque lieu. Une action de copie d'autorisations vers une nouvelle édition doit présenter les correspondances et les accès avant validation.

La révocation centrale doit être effective et vérifiée par les accès caisse, même si une synchronisation locale ou distante est temporairement incomplète. Les opérations externes Fedow et les écritures locales ne forment pas une transaction atomique commune : exposer les synchronisations en attente et les erreurs. Aucun échec ne doit se transformer en autorisation globale implicite.

La carte primaire autorise un opérateur dans un lieu déjà choisi par le terminal. Elle ne change pas le lieu du téléphone. La réutilisation des appareils entre éditions demeure un sujet Discovery/appairage distinct.

## 10. Évolution proposée et validation

Ordre proposé pour une réalisation dans le dépôt, avec commits, tests et builds :

1. Définir le registre des éditions du collectif, le gala live et les permissions complémentaires. Reprendre l'adaptation d'accueil en cours : sa redirection vers un lieu fixe ne doit pas devenir la logique du compte central.
2. Livrer le compte central en lecture seule : authentification, cartes, monnaies locales, historique et états ; accès au seul gala live. Vérifier deux lieux et un même compte sans exposition des données d'autrui ni double comptage.
3. Ajouter la gestion des lieux et des administrateurs : onboarding natif, préparation, désactivation sans suppression, cohérence des droits et passage de session.
4. Ajouter l'inventaire des lots et les autorisations de cartes primaires communes ; tester une carte physique sur deux lieux avec un point de vente autorisé et un refus attendu.
5. Relier chaque monnaie à l'accès au remboursement natif de son lieu, afficher le message des sept jours et exposer aux personnes autorisées la désactivation manuelle native. Conserver le moteur de remboursement existant.
6. Valider la chaîne avec deux éditions distinctes, puis préparer séparément la reprise des cartes/données de production et la bascule DNS/CAWL.

Vérifications structurantes : zéro ou un gala live ; ancien solde visible avec nouveau gala live ; accès au remboursement du bon lieu sans nouvelle demande en attente ; message et date du bon gala ; absence de coupure automatique à J+7 ; remboursement permis nativement avant désactivation puis bloqué après désactivation manuelle ; retrait des droits d'un seul lieu sans casser les autres ; historique et cartes inchangés après désactivation.

Ce document ne remplace pas la preuve réelle d'un parcours NFC ou d'un remboursement CAWL test avec rapprochement. Aucun paiement, remboursement ou message de validation n'est nécessaire pour la présente étude.

## 11. Points restant à arrêter avant réalisation des fonctions concernées

- À quoi mène exactement le bouton participant du gala live : compte natif/recharge ou autre entrée publique ? L'accès administration reste conditionné aux droits.
- Le crédit d'une édition reste-t-il strictement propre à cette édition ? Proposition de cette étude : oui, sans transfert automatique.
- Identifier la date de référence de l'édition à afficher avec le message des sept jours ; cette donnée est informative et ne programme aucune coupure.
- Administrateurs du collectif autorisés à déléguer ce rôle, politique des droits sur les futurs lieux, et périmètre Kfet éventuel.

Ces points n'empêchent pas la conception du socle et la lecture seule. La conservation du mécanisme de remboursement interne, sans nouveau workflow d'attente, est déjà décidée.

## 12. Sources de code consultées

- [Lieux et domaines](../../Customers/models.py), [applications partagées et par lieu](../../TiBillet/settings.py).
- [Compte, droits et remboursement utilisateur](../../BaseBillet/views.py), [permissions](../../ApiBillet/permissions.py), [utilisateur et set_staff](../../AuthBillet/models.py).
- [Portefeuille et monnaies](../../fedow_core/models.py), [services de solde et remboursement](../../fedow_core/services.py).
- [Calcul du remboursable CAWL](../../PaiementCawl/remboursements.py), [prestataire et rapprochement](../../PaiementCawl/services.py).
- [Onboarding](../../onboard/views.py), [ses routes](../../onboard/urls.py), [administration des lieux](../../Administration/admin_tenant.py).
- [Cartes et générations](../../QrcodeCashless/models.py), [administration des cartes](../../QrcodeCashless/admin.py), [cartes primaires](../../laboutik/models.py), [formulaire et contrôles d'origine](../../Administration/admin/laboutik.py).
- [Clôtures de caisse](../../comptabilite/models.py).
