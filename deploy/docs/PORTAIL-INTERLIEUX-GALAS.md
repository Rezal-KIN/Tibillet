# Portail interlieux des Galas — conception

**Étude du 3 novembre 2026.** Les exigences ci-dessous ont été exprimées par l'utilisateur ; les choix techniques proposés restent à implémenter et à tester. Aucun lieu, compte, droit, solde, remboursement ou domaine n'a été modifié pour cette étude.

Les constats de code portent sur le worktree `tibillet-local-upstream`, base `7f1ddb08`, avec l'adaptation d'accueil locale encore non publiée. Aucun nouvel inventaire de VM n'a été effectué pendant cette étude ; les chiffres historiques ci-dessous sont explicitement datés.

Document d'ensemble : [Nouvelle architecture](NOUVELLE-ARCHITECTURE.md).

## 1. Décisions confirmées et périmètre

- Une installation TiBillet commune aux éditions du gala, avec **un lieu natif par édition**. Chaque lieu conserve ses points de vente, catalogue, stocks, ventes et clôtures. Il peut contenir un ou plusieurs événements de billetterie.
- Le domaine principal devient une entrée de services cashless, pas une reprise du site de communication des Galas. L'ancien site sert uniquement de référence visuelle. La billetterie pourra être proposée ultérieurement.
- Les cartes physiques sont réutilisables. Leur adresse imprimée reste `https://galas-am-aix.rezal.fr/qr/<identifiant>` ; préserver UUID QR, numéro et UID NFC.
- Un espace personnel central présente les cartes associées au compte, les monnaies et soldes des différentes éditions, les demandes de remboursement et un accès au seul gala actuellement live.
- Un espace d'administration interlieux permet de créer les lieux avec le parcours natif, les désactiver, gérer les administrateurs, consulter les lots de cartes et attribuer des cartes primaires réutilisables. L'utilisateur a précisé que chaque carte doit avoir un réglage global autorisant ou refusant explicitement les lieux.
- Les remboursements peuvent être demandés **pendant les sept jours suivant la clôture du gala**, puis les montants restants concernés sont indiqués « non réclamés ». Cette interprétation a été explicitement confirmée.
- La production AWS et les adresses imprimées ne basculent pas pendant la conception. CAWL reste en mode test dans l'instance en construction.

Ce choix concerne les éditions Gala. Le regroupement ou non de la Kfet dans cette installation reste à décider séparément ; il ne découle pas de l'accord sur les éditions.

## 2. Parcours utilisateur proposé

```text
Domaine commun → connexion TiBillet → Mon espace
  ├── Ma carte / mes cartes associées
  ├── Mes monnaies et soldes, classés par édition
  ├── Mes demandes de remboursement et leur suivi
  └── Accéder au gala en cours (un seul, s'il existe)

Compte autorisé → Administration du collectif
  ├── Éditions : créer, préparer, sélectionner comme live, clôturer
  ├── Administrateurs et périmètres de droits
  ├── Demandes de remboursement à traiter
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
| Remboursement CAWL | `PaiementCawl.remboursements`, suivi `CawlRefund`, écritures de vente/règlement | Monnaie sélectionnée via le produit actif ; désactiver/archiver la monnaie bloque actuellement les remboursements |
| Clôtures de caisse | `comptabilite.ClotureCaisse` | Rapports périodiques du lieu, pas le cycle de vie métier de l'édition |

La nouvelle interface doit composer ces services, sans dupliquer les identités, les soldes ni le moteur d'encaissement.

## 4. Soldes : une ligne par monnaie, pas une somme trompeuse

Le portefeuille appartient à la personne ; sa carte sert à l'identifier. L'espace présente donc les soldes du portefeuille du compte connecté et les cartes qui y sont réellement associées. Une carte anonyme non associée ne doit pas être rattachée sur la seule connaissance de son numéro.

Pour chaque monnaie : nom, édition émettrice, montant, unité, état, montant encore réclamable et date limite. Séparer les crédits en euros, cadeaux et points. Ne pas présenter un total mélangeant ces unités, ni additionner deux fois une monnaie acceptée dans plusieurs lieux. Pour une monnaie partagée, afficher une seule position et ses lieux d'acceptation.

Les anciennes monnaies doivent rester visibles dans l'historique, même lorsque leur usage ou leur remboursement est fermé. Un montant « non réclamé » n'est plus présenté comme disponible. Les données historiques ne sont pas effacées pour produire ce résultat.

Dans la VM V2, les soldes locaux viennent de `fedow_core`. La migration d'anciennes données AWS et leur rapprochement avec le Fedow distant restent un chantier distinct ; les afficher côte à côte ne prouve pas qu'ils sont indépendants ni additionnables.

La conception proposée conserve une monnaie propre à chaque édition pour rendre son délai et ses montants non réclamés explicites. Un partage de crédit entre éditions reste une décision supplémentaire : s'il est autorisé, il faut définir à quelle édition s'applique l'expiration. Réutiliser une carte ne transfère pas automatiquement ses anciens crédits.

## 5. Cycle de vie d'une édition et choix du gala live

Proposition d'états :

| État | Utilisation et visibilité |
|---|---|
| Préparation | Back-office accessible aux personnes autorisées ; pas d'encaissement public |
| Live | Édition désignée par le bouton public ; caisse et recharge selon les modules autorisés |
| Clôturée — remboursements ouverts | Fin des nouvelles ventes/recharges de cette édition ; soldes et demandes restent accessibles pendant sept jours |
| Terminée — non réclamé | Plus de nouvelle demande ; conservation des soldes historiques, dossiers et écritures |

La clôture du gala est une action métier datée, distincte d'une clôture journalière de caisse. Le serveur fixe `closed_at` et calcule `refund_deadline_at`. Proposition précise : sept jours de 24 heures, instants stockés en UTC, date et heure limites affichées dans le fuseau du gala. La demande est recevable avant l'instant limite, pas à partir de cet instant. Cette convention horaire reste à valider.

La configuration commune désigne explicitement **zéro ou un** lieu live. Aucun choix par `first()`, par événement le plus récent ou par cache ancien. Une bascule met à jour ce choix de façon cohérente avec les états ; un lieu de démonstration, en préparation ou clôturé ne devient pas live implicitement. Si aucun gala n'est live, le compte et les remboursements restent accessibles, et le bouton indique l'absence de gala en cours.

Il peut y avoir simultanément un gala live et des remboursements ouverts pour l'édition précédente. Les demandes de cette dernière restent attachées à cette dernière, même après la bascule.

**Désactiver ne signifie pas supprimer.** Après ouverture, la sortie normale est la clôture métier, puis la fin du délai. Une suspension d'urgence constitue un état opérationnel distinct : elle arrête les nouvelles opérations concernées, sans antidater la clôture ni faire disparaître l'historique. Ne pas utiliser les commandes natives de suppression des lieux inactifs pour cette fonctionnalité.

## 6. Remboursements et non-réclamés

### Règle temporelle

Les demandes utilisateur sont ouvertes entre la clôture du gala et son échéance à J+7. Le montant restant et la date limite sont affichés dans le compte, dans le formulaire de demande et dans l'information fournie lors de la recharge. Le texte est une règle du service à publier, pas une affirmation nouvelle sur sa qualification juridique ou comptable.

Une demande recevable enregistrée à J+6 reste à traiter après J+7. Un retard de l'administrateur ou du prestataire ne transforme pas cette demande en non-réclamé. Séparer les montants disponibles, réservés à une demande, remboursés et non réclamés. Une demande ne réserve jamais plus que le montant éligible restant, même avec plusieurs onglets ou plusieurs essais.

Après l'échéance, seules les nouvelles demandes sont bloquées. Le reliquat sans demande recevable reçoit le statut « non réclamé », avec date, montant et référence d'édition. L'extinction du disponible doit être justifiée par une écriture traçable ; la qualification comptable et l'écriture exacte restent à définir. Ne pas supprimer les transactions ni maquiller ce montant en remboursement réalisé ou en consommation.

L'échéance est contrôlée côté serveur à chaque opération ; elle ne dépend pas seulement du passage d'un timer ou de la visibilité d'un bouton. Les reprises de traitements et la régularisation des paiements déjà engagés restent possibles dans le bon contexte.

### Éligibilité selon l'origine des fonds

Le code CAWL actuel limite le remboursement en ligne au minimum entre le solde de la monnaie et les recharges CAWL de cette personne encore remboursables. Il rend l'argent sur les paiements d'origine. Les crédits issus d'espèces, d'un terminal bancaire externe, de cadeaux ou d'autres monnaies ne deviennent pas remboursables par CAWL du seul fait d'une interface centrale.

Pour couvrir la demande utilisateur, le portail doit pouvoir enregistrer une demande nécessitant un traitement administratif lorsque l'automatisation n'est pas possible. Le moyen de règlement de ce reliquat et la règle pour les crédits offerts restent à décider. Une demande, son acceptation et le versement effectif sont des états distincts ; afficher aussi les refus, les erreurs et les paiements en attente.

**Adaptation indispensable :** le remboursement doit recevoir explicitement l'édition et la monnaie concernées, et utiliser son échéance. Il ne doit plus dépendre de la monnaie de recharge actuellement active. Bloquer l'utilisation pour payer doit être distinct de l'autorisation de remboursement pendant la fenêtre.

La logique doit être appliquée aux routes existantes de remboursement et au vidage en caisse, aux actions administratives concernées et aux tâches ; modifier seulement la nouvelle page laisserait des contournements ou des refus incohérents.

### Suivi du prestataire

Réutiliser les appels CAWL et les écritures natives, en complétant la persistance des demandes, la réservation du montant, l'idempotence et le rapprochement. Le succès HTTP d'un appel ne prouve pas un versement final : CAWL distingue notamment `REFUND_REQUESTED`, `REFUNDED` et `REJECTED`. Une opération incertaine doit être rapprochée avant un nouvel envoi.

Documentation officielle : [états CAWL](https://docs.ecommerce.cawl-solutions.fr/en/integration/api-developer-guide/statuses), [requêtes idempotentes](https://docs.ecommerce.cawl-solutions.fr/en/integration/api-developer-guide/idempotent-requests).

## 7. Authentification, droits et nouveaux administrateurs

Un seul compte TiBillet et son mécanisme d'authentification. Le domaine public ne monte pas actuellement l'espace natif `/my_account/` : il faut développer l'espace central en réutilisant les services appropriés, plutôt que monter tout le back-office d'un lieu sur le schéma public.

Proposition de rôles :

| Rôle | Périmètre |
|---|---|
| Participant | Ses propres cartes, soldes et demandes ; accès public au gala live |
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

1. Définir le registre des éditions du collectif, le gala live, les états, échéances et permissions complémentaires. Reprendre l'adaptation d'accueil en cours : sa redirection vers un lieu fixe ne doit pas devenir la logique du compte central.
2. Livrer le compte central en lecture seule : authentification, cartes, monnaies locales, historique et états ; accès au seul gala live. Vérifier deux lieux et un même compte sans exposition des données d'autrui ni double comptage.
3. Ajouter la gestion des lieux et des administrateurs : onboarding natif, préparation, désactivation sans suppression, cohérence des droits et passage de session.
4. Ajouter l'inventaire des lots et les autorisations de cartes primaires communes ; tester une carte physique sur deux lieux avec un point de vente autorisé et un refus attendu.
5. Implémenter le cycle de remboursement : explicitement par édition/monnaie, demandes horodatées, réservations, traitement CAWL test ou manuel, échéances et non-réclamés traçables.
6. Valider la chaîne avec deux éditions distinctes, puis préparer séparément la reprise des cartes/données de production et la bascule DNS/CAWL.

Vérifications structurantes : zéro ou un gala live ; ancien solde visible avec nouveau gala live ; monnaie inactive mais remboursable pendant la fenêtre ; demande à l'instant limite refusée ; demande recevable conservée après la limite ; absence de double remboursement après double clic, reprise ou réponse CAWL incertaine ; retrait des droits d'un seul lieu sans casser les autres ; fermeture par toutes les routes concernées ; historique et cartes inchangés après désactivation.

Ce document ne remplace pas la preuve réelle d'un parcours NFC ou d'un remboursement CAWL test avec rapprochement. Aucun paiement, remboursement ou message de validation n'est nécessaire pour la présente étude.

## 11. Points restant à arrêter avant réalisation des fonctions concernées

- À quoi mène exactement le bouton participant du gala live : compte natif/recharge ou autre entrée publique ? L'accès administration reste conditionné aux droits.
- Le crédit d'une édition reste-t-il strictement propre à cette édition ? Proposition de cette étude : oui, sans transfert automatique.
- Le délai de sept jours est confirmé ; valider la convention précise des sept fois 24 heures et l'affichage du fuseau.
- Moyen de traitement des demandes pour des recharges non CAWL et règle des crédits offerts ; qui traite ces demandes ?
- Texte public, traitement comptable exact des non-réclamés, et gestion d'une demande recevable mais refusée techniquement après l'échéance.
- Administrateurs du collectif autorisés à déléguer ce rôle, politique des droits sur les futurs lieux, et périmètre Kfet éventuel.

Ces points n'empêchent pas la conception du socle et la lecture seule, mais ne doivent pas être tranchés silencieusement lors du développement financier ou de la délégation de droits.

## 12. Sources de code consultées

- [Lieux et domaines](../../Customers/models.py), [applications partagées et par lieu](../../TiBillet/settings.py).
- [Compte, droits et remboursement utilisateur](../../BaseBillet/views.py), [permissions](../../ApiBillet/permissions.py), [utilisateur et set_staff](../../AuthBillet/models.py).
- [Portefeuille et monnaies](../../fedow_core/models.py), [services de solde et remboursement](../../fedow_core/services.py).
- [Calcul du remboursable CAWL](../../PaiementCawl/remboursements.py), [prestataire et rapprochement](../../PaiementCawl/services.py).
- [Onboarding](../../onboard/views.py), [ses routes](../../onboard/urls.py), [administration des lieux](../../Administration/admin_tenant.py).
- [Cartes et générations](../../QrcodeCashless/models.py), [administration des cartes](../../QrcodeCashless/admin.py), [cartes primaires](../../laboutik/models.py), [formulaire et contrôles d'origine](../../Administration/admin/laboutik.py).
- [Clôtures de caisse](../../comptabilite/models.py).
