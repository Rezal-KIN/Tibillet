# Intégration aux images, cartes NFC sans QR et dépôt CSV

> Ce document conserve l’état de la préparation locale. La livraison dans main, Foundation et les vérifications AWS sont décrites dans [l’audit de livraison sur un gala neuf](2026-10-08-pipeline-images-csv-gala-neuf.md).

## Décision et périmètre

L'utilisateur privilégie le fonctionnement TiBillet natif et une petite quantité
de code compréhensible. Les montages utilisés par TiBillet pour les données,
Nginx et Redis peuvent rester. Les remplacements de code ajoutés pour Gala
doivent être intégrés aux images.

Cette préparation locale conserve les cartes NFC sans QR, les réglages email,
les liens vers les sources et la reprise d'installation déjà présente. Elle
ne crée pas un second système d'enregistrement de cartes. Elle ne change ni
les sauvegardes ni la configuration Nginx. Aucun changement AWS ou déploiement
d'instance n'a été réalisé pendant ce travail.

## Ce qui a été préparé

- Deux Dockerfiles dérivent des images TiBillet exactes déjà auditées, sans
  nouvelle installation des dépendances : [`Fedow`](../../deploy/Fedow/Dockerfile)
  et [`LaBoutik`](../../deploy/Laboutik/Dockerfile).
- LaBoutik embarque les quatre fichiers Python et les quatre templates
  versionnés déjà examinés. Les trois fonctions de cartes, installation et
  email conservent leur comportement antérieur.
- Fedow embarque les réglages et le template de sources. Les écarts DEBUG sont
  repris du code natif exact ; seul le chemin de templates et la notice diffèrent
  encore dans ses réglages. SQLite, serializers et dashboard restent natifs.
- Les dix bind mounts Python/templates sont retirés des Compose actifs du
  dépôt. Les fichiers de sources restent versionnés et sont copiés au build.
- Le build Test prépare désormais Lespass, Fedow et LaBoutik. Terraform ajoute
  seulement les deux dépôts ECR nécessaires et les droits de publication/lecture
  correspondants. Ces ressources ne sont pas encore appliquées sur AWS.
- Le manifeste conserve les images construites et leurs bases natives sous
  `image_builds`. La promotion exige les mêmes images et références que Smoke.
- Avant démarrage, les labels du commit et de l'image de base sont vérifiés.
  La publication des sources inclut les fichiers intégrés aux images, même
  lorsqu'aucun montage de code n'existe. Les anciens manifests restent
  compréhensibles par les outils de publication.
- Le build réutilise les comparaisons exactes avec les archives TiBillet et
  refuse des écarts de réglages hors du périmètre email/templates.

Les changements se trouvent dans le workspace sur la branche existante.
Les images locales sont des essais du travail non committé, pas des releases
publiées. Le serveur Smoke garde donc encore ses anciens montages tant que
la nouvelle chaîne n'a pas été livrée.

## Deux usages des cartes à conserver séparément

**Lot avec identités physiques fournies par CSV :** la commande native Fedow
`import_cards` renseigne le QR, le numéro imprimé et le NFC. Le mécanisme actuel
de validation/import des trois lots, 7 020 cartes, reste inchangé.

**Carte NFC classique absente du catalogue et sans QR imprimé :** les deux
fonctions LaBoutik déjà présentes créent la carte après une absence Fedow
confirmée, puis exigent une relecture réussie. Elles restent dans l'image.
L'identifiant QR interne généré sert au modèle TiBillet ; aucun QR physique
n'est requis pour utiliser la carte sur le lecteur.

L'enregistrement au scan ne remplace pas un catalogue usine : il ne peut pas
deviner les identités imprimées d'une carte qui possède en réalité un QR.
Les lots usine restent à importer avant utilisation.

## Déposer les CSV dans AWS : possible sans application supplémentaire

La console S3 offre déjà un dépôt de fichiers par glisser-déposer :
[procédure officielle AWS](https://docs.aws.amazon.com/AmazonS3/latest/userguide/upload-objects.html).
Le chemin simple est un dossier privé de lots de cartes, une validation dans
la pipeline et l'import natif au démarrage du nouveau gala. Ajouter un
formulaire à l'intérieur de la console CodePipeline demanderait une autre
interface ou une intégration particulière ; ce n'est pas recommandé ici.

**Le dépôt libre de nouveaux CSV n'est pas encore raccordé automatiquement.**
Aujourd'hui, la pipeline lit le catalogue versionné `deploy/card-stock.json` et
les fichiers exacts désignés par leurs empreintes. Un nouveau fichier déposé
dans S3 ne sera pas importé simplement parce qu'il est présent.

Le futur raccordement doit figer les fichiers sélectionnés pour chaque
exécution, garder leur génération et vérifier leur format/associations. Test
et Production doivent utiliser le même lot. Les identifiants de release et
de preuve de Test sont actuellement liés au commit ; sélectionner de nouveaux
CSV sans modifier le code nécessite aussi de distinguer les versions de
catalogue dans ces identifiants. Il s'agit d'une adaptation de pipeline,
indépendante du moteur financier TiBillet, à spécifier avant implementation.

Cette proposition de dépôt S3 n'a pas créé de dossier, changé d'IAM pour les
CSV, choisi de nouveau fichier ou exécuté d'import.

## Contrôles locaux

- Construction Docker effective des deux images, plateforme `linux/amd64`.
- Contrôle des dix fichiers copiés dans les images par SHA-256, sans montage
  de code et sans lancer les applications ou leurs migrations.
- 23 tests dans l'image LaBoutik réelle : cartes connues/inconnues, refus des
  erreurs réseau/authentification, prix, billetterie/adhésions et reprise
  d'installation. HTTP et ORM restent simulés : aucun paiement ni envoi mail.
- 129 tests de déploiement : 126 réussis, trois contrôles dépendants de Linux
  ignorés sur le Mac. Les nouveaux contrôles couvrent les sources des images,
  leur transfert au manifeste, la promotion et le refus de labels incohérents.
- Comparaison exacte des sources natives : ancienne dérive métier absente,
  SQLite natif, réglages limités aux changements choisis.
- `terraform validate` réussi, sans backend et sans plan/apply AWS.
- Configuration Docker Compose des trois applications validée : aucun montage
  Python/HTML. Les répertoires de données et les configurations Nginx restent.

Les reçus et logs locaux sont conservés sous
`.context/image-integration-20261008/`. Ces contrôles ne constituent pas le
test de premier démarrage de la prochaine release sur une EC2 neuve.

## Travail restant dans l'ordre

1. Revoir les modifications locales puis les intégrer au code utilisé par la
   pipeline principale.
2. Appliquer Foundation pour les deux dépôts ECR et les permissions associées,
   puis lancer Test avec les nouvelles images.
3. Vérifier un gala neuf par la pipeline : import des lots, carte NFC sans QR,
   QR, emails et caisse. Respecter l'approbation de production existante.
4. Pour les futurs lots déposés librement : retenir le dossier S3 et raccorder
   la sélection/version du catalogue, sans ajouter de formulaire TiBillet.
