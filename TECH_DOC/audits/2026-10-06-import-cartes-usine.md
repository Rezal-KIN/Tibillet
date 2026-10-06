# Cartes physiques Gala : fichiers usine et import natif

## Résultat vérifié le 6 octobre 2026

L'image Fedow actuellement déployée sur **Smoke** contient la commande native
`python manage.py import_cards`. Elle sait importer l'association entre l'URL du
QR, le numéro imprimé et l'identifiant NFC. Aucun nouvel importeur ni montage de
code n'est nécessaire pour enregistrer ces lots.

LaBoutik contient aussi `python manage.py import_csv_card`, mais cette commande
crée uniquement des `CarteCashless` locales. À elle seule, elle n'enregistre pas
les cartes dans Fedow et ne suffit donc pas à ouvrir les QR côté Lespass.

Cet audit n'a exécuté aucun import, créé aucune carte et modifié aucune base
sur les instances déployées.
Les deux fichiers Excel originaux n'ont pas été modifiés.
L'implémentation ajoutée ensuite a été testée sur des bases SQLite isolées ; elle
n'a pas encore importé ces lots sur AWS (voir le statut en fin de document).

## Fichiers fournis et vérification de toutes les lignes

| Fichier | Cartes | SHA-256 |
|---|---:|---|
| `2609171881---- white.xlsx` | 1 755 | `ab0a36383ba95066e88c9bcaddd505efffe3b2306eb266bd72cc512906e79b7a` |
| `2609171881---black.xlsx` | 1 755 | `f11c1fe83939e485c8515f5aa95d90332e78699767facd2d94033f16d61c364c` |

Les classeurs ont chacun une feuille, une ligne d'en-tête et 1 755 lignes de
données. Total : **3 510 cartes**. Aucune formule. Aucun doublon, entre les deux
lots inclus, sur les UUID QR, les numéros imprimés, les UID directs, les UID
inversés ou les blocs usine. Aucune collision entre les ensembles d'UID directs
et inversés.

Toutes les URLs utilisent `https://galas-am-aix.rezal.fr/qr/<UUID v4>`. Chaque
numéro imprimé correspond aux huit premiers caractères de cet UUID, en
majuscules. Les représentations hexadécimales et décimales de l'UID sont
cohérentes entre elles ; les quatre premiers octets du bloc usine correspondent
à la colonne D et leur octet de contrôle XOR est cohérent.

| Colonne | En-tête usine | Contenu / usage |
|---|---|---|
| A | `原始码` | Bloc usine de 16 octets, soit 32 caractères hexadécimaux ; ne pas le confondre avec l'UID de 8 caractères attendu par TiBillet. |
| B | `二维码` | URL exacte du QR imprimé, à conserver. |
| C | `文本` | Numéro imprimé, à conserver. |
| D | `8H正` | UID NFC de quatre octets, en hexadécimal dans l'ordre du bloc usine. |
| E | `8H反` | Le même UID, avec l'ordre des quatre octets inversé. |
| F | `8H10D正` | Valeur décimale de D, sur dix caractères. |
| G | `8H10D反` | Valeur décimale de E, sur dix caractères. |

Le candidat CSV natif est **B, C, D**, sous réserve de confirmer l'ordre des
octets sur le lecteur réellement utilisé. Si le lecteur transmet E, la troisième
colonne doit contenir E. Le frontend LaBoutik met le tag reçu en majuscules et
vérifie sa longueur de huit caractères ; il ne corrige pas automatiquement
l'ordre des octets. Le mode Cordova transmet `nfc.bytesToHexString(tag.id)` ; le
mode lecteur local transmet le tag reçu du serveur NFC.

## Vérification sur l'instance active

Le paramètre AWS `/tibillet-gala-paris/active-gala` vaut `gala-smoke`.
SSM a exécuté uniquement des lectures de fichiers et des requêtes ORM `values`.
Commande : `11241d81-6dbe-4beb-8efd-f5c1ddd82aa3`, état `Success`.

| Base Smoke | Cartes déjà présentes | Recoupements avec les fichiers usine |
|---|---:|---:|
| Fedow | 4 | 0 |
| LaBoutik | 3 | 0 |

La comparaison porte sur les **3 510 lignes**, et sur les trois identifiants :
UUID QR, numéro imprimé, UID NFC. Les deux ordres NFC D/E ont été examinés.
Les projections des deux bases étaient complètes. Ces lots ne sont donc pas
enregistrés dans Smoke et aucun conflit avec les cartes existantes n'a été
constaté lors de cette lecture. Refaire cette vérification juste avant un import.

La carte précédemment signalée,
`87b51016-91a9-4f2a-8c6b-c759ca5c6af6`, n'apparaît dans **aucun des deux
classeurs**, ni dans les bases Smoke déjà vérifiées. L'import de ces seuls lots
ne permettra pas de retrouver son association NFC. Il faut identifier son lot
d'origine ou relever ensemble son QR imprimé et son UID physique.

La présence des cartes dans Aix n'a pas été vérifiée : la tentative SSM
précédente était `Undeliverable` (`ConnectionLost`). Une absence dans Smoke ne
permet pas de conclure sur Aix.

## Comportement des deux commandes natives

### Fedow : `import_cards`

Fichier dans l'image :
`/home/fedow/Fedow/fedow_core/management/commands/import_cards.py`.
SHA-256 vérifié dans l'image et identique à la source de référence locale :
`cf1217b46eacd7f8e85ef71c6c5e6df79ec6e03baeb422030e38dabc001c30a6`.

- Attend un **CSV séparé par des virgules, sans ligne d'en-tête**, avec trois
  colonnes : `URL_QR,NUMERO_IMPRIME,UID_NFC_HEXA_8_CARACTERES`.
- Extrait l'UUID après `/qr/` ; ne génère pas un nouveau QR.
- Valide l'URL, les longueurs et les doublons dans le fichier et dans Fedow.
- Demande le lieu d'origine, puis le numéro de génération du lot.
- Crée `Origin` et les `Card` dans une transaction Django `@atomic`.
- Aucun appel de recharge ni création monétaire dans la commande. Le wallet
  anonyme est créé ultérieurement par le mécanisme natif `Card.get_wallet()`.
- Ne possède pas d'option native `--dry-run`. Un lot déjà importé est rejeté
  comme doublon ; la commande n'est pas un import à rejouer à chaque déploiement.

Les futures exécutions doivent choisir le lieu apparié à LaBoutik et Lespass,
actuellement `Festival` sur Smoke, domaine `galas-am-aix.rezal.fr` ; ne pas
supposer que l'index du lieu ou son UUID sont identiques sur une nouvelle base.

### LaBoutik : `import_csv_card`

Fichier dans l'image :
`/DjangoFiles/administration/management/commands/import_csv_card.py`.
SHA-256 vérifié :
`7e97b54cb79637b987148095decaf9c7a02c6c98fd36d6b2049fbe8a257da7c4`.

Attend les trois mêmes colonnes, extrait le même UUID puis crée les objets
locaux. Ne choisit pas de lieu/génération, n'appelle pas l'API Fedow, et ne
dispose pas des validations de lot ni de la transaction globale de la commande
Fedow. Ne pas exécuter systématiquement les deux importeurs : après un import
Fedow, la lecture native LaBoutik (`NFCCard.retrieve` / `CardValidator`) récupère
les identifiants Fedow et matérialise la carte locale au premier scan.

## Proposition simple, non exécutée

1. Confirmer D/E avec un UID relevé sur une carte de l'un des deux lots et le
   lecteur prévu pour le gala ; vérifier le QR et le numéro imprimé de cette
   même carte. Le matériel physique n'a pas été testé pendant cet audit.
2. Préparer des CSV B/C/UID sans en-tête, sans régénérer les UUID ; refaire la
   comparaison avec la base cible et conserver un point de restauration.
3. Utiliser **la commande native Fedow inchangée**, une seule fois par base
   neuve/lot. Vérifier ensuite un QR imprimé et la synchronisation NFC dans
   LaBoutik. L'intégration éventuelle de cette initialisation dans la pipeline
   restait à définir à ce stade de l'audit ; elle est implémentée dans la section
   ajoutée ci-dessous après autorisation.

L'enregistrement automatique actuellement conservé dans LaBoutik crée un UUID
QR aléatoire pour une carte inconnue. Il ne peut pas retrouver un QR préimprimé
à partir du seul UID NFC. L'import usine avant utilisation de ces cartes évite
cette divergence, sans modifier ce code.

## Import automatique pour les futurs événements : proposition

Demande complémentaire de l'utilisateur : toutes les nouvelles instances doivent
pouvoir initialiser automatiquement le stock physique, notamment les cartes
conservées d'anciens galas. **Cette section conserve la proposition initiale.
L'implémentation autorisée ensuite est décrite ci-dessous ; l'activation des
lots usine reste en attente d'une lecture physique.**

### Données de stock communes, bases d'événement distinctes

Conserver un catalogue de lots contenant uniquement les associations fixes
`UUID QR / numéro imprimé / UID NFC`. Les classeurs usine restent les originaux
archivés. Une conversion validée produit des CSV au format natif, avec les mêmes
UUID et numéros. Les CSV sont conservés dans le stockage S3 privé déjà utilisé
par la pipeline, sous un préfixe dédié au stock ; chaque version du catalogue
référence les empreintes SHA-256 et les nombres de lignes des lots. La release
doit référencer une version précise, pour que le test et le déploiement lisent
exactement les mêmes données, sans téléchargement d'un fichier `latest` mutable.

Le catalogue est commun aux futurs événements ; il ne contient ni participants,
ni comptes, ni soldes. Chaque base d'événement conserve ses propres utilisateurs
et opérations. Réutiliser une carte physique sur une **nouvelle base indépendante**
réimporte son identité, pas le portefeuille de l'ancien événement. Un simple
redéploiement d'une base existante conserve les comptes et les soldes.

### Étape d'initialisation et de rattrapage

Ajouter un petit outil de déploiement, appelé par `deploy-release.sh` après
l'initialisation Lespass/LaBoutik et leur appairage Fedow, avant que le déploiement
soit déclaré prêt. L'outil est installé par `install-runtime-contract.sh` comme
les autres dépendances runtime, et intégré aux tests du contrat de déploiement.
Les droits AWS des instances sont limités à la lecture du préfixe de catalogue.

Pour chaque lot de la version sélectionnée :

1. Vérifier l'empreinte du CSV et ses associations, puis comparer les trois
   identifiants à la base Fedow cible.
2. Conserver les cartes qui correspondent exactement ; ne pas toucher à leurs
   utilisateurs, wallets, soldes ou transactions.
3. Préparer un CSV temporaire contenant uniquement les cartes entièrement
   absentes. En cas d'identifiants déjà présents avec une association différente,
   arrêter le déploiement avec une erreur précise, sans écrasement automatique.
4. Appeler **la commande native `import_cards` inchangée**, avec le lieu Fedow
   apparié découvert par son UUID et le numéro de génération du lot. La petite
   enveloppe fournit les réponses aux invites ; elle ne réimplémente pas les
   créations de cartes. Contrôler le lieu et les associations dans la même
   transaction que l'appel natif, pour ne pas valider un import mal orienté.
5. Vérifier les associations et les nombres attendus avant de déclarer la release
   prête. La comparaison avec la base, plutôt qu'un simple fichier « déjà fait »,
   rend une reprise ou un redéploiement sans effet sur les cartes déjà importées.

LaBoutik matérialise ensuite les cartes lors de ses lectures natives de Fedow.
Il n'y a pas de nouvel importeur Django, pas de remplacement d'un fichier Fedow,
pas de montage de CSV permanent dans Compose et pas de modification du paiement.
Un nouveau lot ajouté au catalogue est importable sur une instance existante sans
réinitialiser les lots précédents.

### Domaine imprimé et sélection de l'instance

`deploy/docs/operations/active-gala-and-shared-integrations.md` définit déjà des
noms publics communs à toutes les instances, dont `galas-am-aix.rezal.fr`, et une
bascule vers un seul gala actif. Dans ce cadre, les QR imprimés restent identiques
et suivent l'événement sélectionné. L'import ne bascule pas le trafic public.

Si un futur événement utilise un autre domaine, il faut conserver l'ancien
domaine imprimé comme point d'entrée et prévoir son routage vers l'événement
voulu ; modifier seulement le CSV ne modifie pas l'impression physique. Un QR
avec cette URL commune ne sélectionne pas simultanément plusieurs galas
indépendants : il ouvre celui qui sert actuellement ce domaine.

### Validation prévue et prérequis restants

- Base neuve : tous les lots sélectionnés sont présents après le premier passage.
- Deuxième passage : aucun doublon et aucune modification des cartes, comptes ou
  soldes déjà présents.
- Nouveau lot ou interruption entre lots : seuls les enregistrements manquants
  sont importés au passage suivant.
- Association conflictuelle : erreur explicite et absence d'écrasement.
- Test réel sur une instance neuve de la pipeline : QR physique, puis NFC de la
  même carte ; les mêmes identifiants doivent désigner la même carte.

La confirmation physique de l'ordre D/E reste nécessaire avant de publier le
premier catalogue utilisable. Les cartes d'anciens galas absentes des deux fichiers
fournis nécessitent leurs associations de stock ; aucun UID ne sera inventé à
partir d'un QR. Ces associations peuvent être ajoutées comme lots ultérieurs.

## Implémentation du 6 octobre 2026

L'appel automatique est ajouté à `deploy/tools/runtime/deploy-release.sh`, après
installation/appairage et avant santé/sauvegarde initiale. Les helpers sont
explicitement installés par `install-runtime-contract.sh`.

`import-gala-card-stock.py` vérifie et télécharge temporairement les lots.
`import_card_stock_fedow.py` compare les associations puis appelle
**`import_cards` natif inchangé** dans une transaction couvrant tout le catalogue.
Il vérifie les cartes et leur origine après chaque appel. Les relances préservent
les cartes existantes ; un conflit ou une erreur annule les ajouts du passage.
Les requêtes sont découpées pour respecter les limites SQLite.

`deploy/card-stock.json` contient les seules métadonnées des lots. Son contenu
est copié en entier dans la release Smoke, puis comparé à la release Production.
La version du catalogue est donc celle de la release testée et de son commit,
avec les SHA-256 de chaque CSV ; aucun pointeur mutable n'est utilisé.
`publish-card-stock.py` publie les CSV privés sous des clés dérivées de leurs
octets, sans remplacement, et écrit les métadonnées. Le droit runtime Terraform
est limité à la lecture S3 du préfixe `card-stock/`. Le garde-fou Foundation
autorise uniquement l'ajout exact de cette permission aux rôles existants.

**Aucun modèle, migration, importeur ou fichier Compose TiBillet n'est modifié.
Aucun nouveau montage de code ou de données n'est ajouté.** L'entrée du wrapper
est transmise au shell Django ; les CSV temporaires sont supprimés après usage.

Les variantes D et E des deux lots sont préparées, validées et conservées
localement sous `.context/qr-card-investigation/draft-stock/`. Chacune représente
les mêmes 3 510 cartes. Le catalogue versionné est volontairement vide :
l'utilisateur n'a pas de carte/lecteur disponible pour confirmer D/E à ce stade.
Ces variantes ne sont ni publiées dans S3 ni activées dans une release.

Le [mode opératoire](../../deploy/docs/operations/card-stock-import.md) décrit
la publication, le déploiement, les conflits et le retour arrière.

### Vérifications et livraison

- Suite de déploiement : 121 tests réussis, dont les régressions SQLite utilisant
  la commande native extraite de l'archive TiBillet vérifiée par SHA-256.
- Essai additionnel sur **toutes les 3 510 associations** dans chaque variante
  D et E : 3 510 cartes créées au premier passage, zéro au suivant ; compte et
  solde de test préservés. Chaque variante est essayée sur sa propre base SQLite
  isolée. Reçu local : `native-factory-probe-result.json`.
- Scénarios synthétiques : lot supplémentaire, carte manquante, conflit QR/NFC/
  numéro, interruption sur le second lot, mauvaise origine native ; les erreurs
  annulent les ajouts et préservent les données préexistantes.
- Artefact Production testé sans checkout : le validateur et sa dépendance
  `card_stock.py` sont présents et fonctionnels dans les fichiers livrés.
- Syntaxe Python/shell, `terraform fmt -check`, `terraform validate` et contrôle
  des sept unités TiBillet restaurées réussis.

Ces résultats sont **locaux**, sans modification AWS. Il reste à confirmer D/E,
publier les CSV privés et versionner leurs métadonnées, mettre à jour le contrat
Terraform/CodeBuild via Foundation, puis exécuter la pipeline et tester QR/NFC
sur le matériel. Aucun import sur Smoke/Aix ni bascule publique n'est revendiqué.

## Ajout du CSV Gala G1 le 6 octobre 2026

L'utilisateur a fourni `gala-am-G1.csv`, 308 880 octets, **3 510 lignes**, trois
colonnes sans en-tête au format natif `URL_QR,NUMERO_IMPRIME,UID_NFC`.
SHA-256 : `de7b01ae32c3b25f58c5994665dde545b54aae672e515b4a31f90615eeb91567`.
Toutes les lignes passent le validateur. Aucun doublon interne, ni intersection
avec les classeurs blancs/noirs sur les QR, numéros imprimés ou UID NFC D/E.
Le stock connu totalise donc **7 020 cartes distinctes**.

La carte QR précédemment absente des deux classeurs,
`87b51016-91a9-4f2a-8c6b-c759ca5c6af6`, est présente dans G1. L'association
usine est retrouvée ; aucun nouvel UUID ou UID n'est généré. Cela ne prouve pas
encore que cette carte est enregistrée dans une base déployée.

G1 est repris **octet pour octet**, avec sa colonne NFC unique. Il est publié
sous `card-stock/<sha256>.csv` dans le bucket privé
`tibillet-gala-paris-production-318629836660-backups`, région `eu-west-3`.
Le compte `318629836660` a été vérifié par STS avec le profil `gala-elevated` ;
les quatre protections d'accès public S3 sont activées. La relecture S3 a
confirmé les mêmes octets, le SHA-256 et les 3 510 lignes.

`deploy/card-stock.json` sélectionne désormais **G1, génération 1**. Les deux
lots issus des classeurs restent en attente de lecture physique D/E ; ils ne
sont pas retirés des brouillons ni incorporés avec un ordre supposé. La future
release fige G1 dans son manifeste et le mécanisme natif importe ce lot sur
chaque base cible, sans montage supplémentaire ni modification TiBillet.

L'essai G1 avec la commande native vérifiée sur une base SQLite isolée a créé
3 510 cartes en génération 1, puis zéro à la relance ; le compte et le solde
de test sont préservés. Aucune base Smoke/Aix n'a été modifiée pendant cet ajout.
La mise à jour Foundation des droits/buildspecs puis la livraison par la pipeline
restent nécessaires avant le contrôle de cette carte QR et de son NFC sur une
instance déployée. La publication S3 seule ne supprime pas la 404 actuelle.

Reçus locaux : `gala-am-G1-audit.json`, `gala-am-G1-native-probe-result.json`,
`gala-am-G1-publication-receipt.json`, sous `.context/qr-card-investigation/`.
Le CSV complet reste hors Git et hors archives publiques de sources.

## Éléments d'audit locaux

Sous `.context/qr-card-investigation/` (gitignoré) :

- `audit_factory_workbooks.py`, `factory-workbooks-audit.json` : lecture et
  validation des données, empreintes des originaux.
- `factory-card-records.json` : associations extraites des fichiers fournis,
  avec feuille et ligne d'origine ; données non ajoutées au dépôt.
- `importer-probe-parameters.json`, `importer-probe-command.json`,
  `importer-probe-result.json` : preuve runtime en lecture seule.
- `factory-runtime-comparison.json` : comparaison complète avec Smoke.

Sources de référence inspectées :
`fedow_core/management/commands/import_cards.py`,
`administration/management/commands/import_csv_card.py`,
`fedow_core/models.py:Card`, `fedow_connect/validators.py:CardValidator`,
`fedow_connect/fedow_api.py:NFCCard.retrieve`,
`webview/static/webview/js/lecteur_nfc.js`.
