# Import automatique du stock de cartes

Chaque release peut initialiser les identités physiques des cartes avec la
commande **native Fedow `import_cards`**. Le code de cette commande reste celui
de l'image de référence. Aucun fichier applicatif ni CSV n'est monté en volume
pour cet import ; l'enveloppe de déploiement est exécutée via `manage.py shell`.

## État du stock fourni

Le CSV `gala-am-G1.csv` contient **3 510 cartes**, au format natif sans en-tête.
Il est publié dans le bucket privé et sélectionné comme génération 1 dans
`deploy/card-stock.json`, avec les UID NFC fournis, sans transformation. Son
SHA-256 est `de7b01ae32c3b25f58c5994665dde545b54aae672e515b4a31f90615eeb91567`.
**G1 a été importé sur Smoke le 6 octobre 2026 : ses 3 510 associations sont
vérifiées**, avec sauvegardes avant/après et conservation des données existantes.
L'opération a créé 3 509 cartes et aligné le QR/numéro d'une carte précédemment
enregistrée avec une identité aléatoire, après inspection de ses liens.
Les contrôles HTTPS et API NFC native réussissent sur deux cartes.
Les détails sont dans [l'audit](../../../TECH_DOC/audits/2026-10-06-import-cartes-usine.md).
Aix n'a pas été modifié.

L'import automatique reste à livrer par les releases utilisant ce catalogue,
après livraison du contrat runtime/CodeBuild décrit ci-dessous. Sa sélection
n'exécute pas un import sur une instance déjà lancée.

Les deux classeurs blancs/noirs contiennent **3 510 autres cartes**, sans
recoupement QR/numéro/NFC avec G1 dans aucun des deux ordres D/E. Total connu :
**7 020 cartes distinctes**. Les variantes CSV D/E des classeurs sont préparées
sous `.context/qr-card-investigation/draft-stock/`, hors Git. Elles ont passé le
validateur et un import natif sur SQLite isolé. **L'ordre NFC de ces classeurs
reste à confirmer sur le lecteur physique** ; ils ne sont pas encore sélectionnés
dans le catalogue. Le CSV G1 contient déjà une seule colonne NFC désignée.

Une seule carte suffit à cette confirmation : comparer son numéro imprimé et
l'UID lu au relevé usine. Le fichier donne D et E, qui inversent l'ordre des
quatre octets. Choisir la variante correspondant à l'UID effectivement reçu par
LaBoutik. Conserver le résultat et le type de lecteur dans l'audit.

La carte QR `87b51016-91a9-4f2a-8c6b-c759ca5c6af6`, absente des classeurs, a été
retrouvée dans **G1**. Son QR ouvre maintenant la page de liaison sur Smoke
(HTTPS 200), après import. La présence du lot sur d'autres instances doit être
vérifiée séparément.

## Ajouter ou activer des lots

1. Préparer les CSV natifs : trois colonnes `URL_QR,NUMERO_IMPRIME,UID_NFC`,
   virgules, UTF-8, **sans en-tête**, numéro de huit caractères en majuscules,
   UID de huit caractères hexadécimaux en majuscules. Conserver les UUID et
   numéros imprimés. Ne jamais ajouter les CSV ni les XLSX au dépôt public.
2. Publier les lots dans le bucket privé existant. Le profil et la région sont
   explicites ; l'outil vérifie d'abord le compte AWS Gala. Exemple après
   confirmation de D, avec le nom réel du bucket de releases :

   ```bash
   python3 deploy/tools/publish-card-stock.py \
     --profile gala-elevated --region eu-west-3 \
     --bucket <bucket-de-releases> --domain galas-am-aix.rezal.fr \
     --lot 1 .context/attachments/vvroK1/gala-am-G1.csv \
     --lot 1 .context/qr-card-investigation/draft-stock/D-direct/white.csv \
     --lot 2 .context/qr-card-investigation/draft-stock/D-direct/black.csv \
     --output deploy/card-stock.json
   ```

   L'outil valide tous les lots et les doublons entre lots avant publication.
   Chaque CSV est nommé `card-stock/<sha256>.csv` et écrit avec une condition
   d'absence. Une relance accepte uniquement des octets identiques. Le catalogue
   public ne contient que la clé S3, le SHA-256, le nombre de cartes et la
   génération ; aucun UID NFC, UUID QR ou compte participant.

   Pour ajouter un lot, fournir aussi les lots précédents que l'on souhaite
   conserver dans le catalogue. `--output` décrit l'ensemble des lots sélectionnés.
3. Versionner ce catalogue avec la release. La pipeline Test l'inclut en entier
   dans le manifeste Smoke. La promotion compare le champ `card_stock` complet
   au test réussi, en plus du commit et des quatre images. Les lots testés ne
   peuvent donc pas être remplacés par un `latest` avant Production.
4. Mettre à jour via Foundation les buildspecs CodeBuild Test et
   `Production Validate` (ils sont enregistrés dans la configuration Terraform),
   ainsi que le droit runtime `ReadOnlySharedCardStock`, limité
   à `s3:GetObject` sur le préfixe `card-stock/` du même bucket. Les instances
   n'ont aucun droit d'écriture ni de liste sur ce stock. Pour les instances
   existantes, le contrôleur du plan accepte uniquement cet ajout exact, sans
   modification des autres permissions. L'artefact de validation inclut aussi
   `card_stock.py`, nécessaire au validateur Production. Cet apply est à faire
   avant la première promotion utilisant ce nouvel outillage. Les nouvelles instances reçoivent ce droit dans
   leur configuration Terraform normale.
5. Déployer la release par la pipeline, puis vérifier un QR imprimé et le NFC
   de cette même carte. La mise en place du code et les tests locaux ne prouvent
   pas ce contrôle matériel ni un déploiement AWS réussi.

## Ce qui se passe au démarrage

`deploy-release.sh` appelle `import-gala-card-stock.py` après l'installation
Lespass/LaBoutik, l'appairage Fedow et la configuration des comptes admin, avant
le contrôle de santé et la sauvegarde initiale.

L'outil télécharge temporairement chaque CSV, vérifie ses octets par SHA-256,
ses lignes, le domaine imprimé et les trois identifiants. Il découvre le lieu
Fedow depuis la configuration du tenant Lespass, par UUID de lieu et de wallet.
Il ne choisit pas un lieu à partir d'un index codé en dur.

Dans une transaction Fedow couvrant **tous** les lots sélectionnés :

- Une association QR/numéro/NFC entièrement identique reste intacte, avec son
  UUID de carte, son origine, ses utilisateurs et son portefeuille actuels.
- Une association entièrement absente est ajoutée à un CSV temporaire dans le
  conteneur. L'outil répond aux trois invites de `import_cards` et appelle cette
  commande native. Il contrôle ensuite l'origine et les identifiants créés.
- Une présence partielle ou contradictoire arrête le déploiement. Aucun
  écrasement, suppression, fusion ou nouvelle identité n'est tenté.
- Une erreur native, un changement des invites ou une mauvaise origine annule
  la transaction, y compris les ajouts des lots précédents de ce passage.

Une relance consulte les données réelles, sans marqueur « déjà importé ».
Elle rattrape uniquement les cartes absentes. Les journaux contiennent le nombre
de cartes, pas le stock complet d'UID et de QR. LaBoutik récupère ensuite les
cartes via son mécanisme natif Fedow lors des scans ; son importeur local n'est
pas exécuté en double.

Sur une **base neuve indépendante**, seuls les identifiants physiques sont
réimportés : les comptes, soldes et transactions de l'ancien gala ne sont pas
transférés. Sur la même base, ils sont préservés. L'import ne crée aucun crédit.

## Retour arrière et diagnostic

Restaurer un catalogue antérieur, ou vide, arrête les imports supplémentaires
mais **ne supprime pas les cartes déjà enregistrées**. Un rollback applicatif
avec un ancien manifeste sans `card_stock` reste accepté. Toute suppression de
carte ou de base serait une opération distincte.

Une erreur `conflicts with Fedow` donne le numéro imprimé de la carte à examiner.
Ne pas effacer automatiquement son wallet ou réécrire son UID pour débloquer
l'import. Vérifier la provenance du lot, le sens des octets et les trois
identifiants présents dans Fedow. Une erreur de checksum, de domaine ou de droits
S3 doit être corrigée dans le catalogue/la configuration puis retestée.

Les QR imprimés continuent d'utiliser leur domaine d'origine. Le domaine commun
ouvre le gala actif ; l'import ne change ni DNS ni sélection du gala.
Pour un autre domaine, conserver le routage de l'ancien domaine imprimé.

Validation automatisée : `test_card_stock.py` utilise la commande native
extraite de l'archive TiBillet avec son SHA-256 vérifié, sur SQLite isolé.
Les contrôles couvrent l'import neuf, une relance, des cartes manquantes, un
nouveau lot, les conflits, une interruption et l'annulation d'une mauvaise
origine, ainsi que la préservation d'un compte et de son solde.
