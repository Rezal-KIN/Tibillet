# Livraison des images et import S3 sur un gala neuf — 8 octobre 2026

La préparation décrite dans `2026-10-08-integration-images.md` a été livrée dans `main` par la PR #104. Le commit applicatif testé est `9bece97e3303a89bff04eacd115e920311c63405`.

## Dépôt CSV

Le dossier privé `s3://tibillet-gala-paris-production-318629836660-backups/card-stock/uploads/` contient les trois CSV natifs vérifiés : génération 1/G1, 3 510 cartes ; génération 2/blanc, 1 755 ; génération 3/noir, 1 755. Les fichiers ont été repris octet pour octet des objets immuables validés précédemment, après confirmation physique des colonnes NFC/numéro imprimé. Aucun classeur ou identifiant privé de carte n'est ajouté aux archives publiques.

La console S3 permet leur dépôt par glisser-déposer. Placer chaque nouveau CSV dans `<génération>/<nom>.csv`, puis lancer Test. Le format est UTF-8, trois colonnes sans en-tête : URL QR, numéro imprimé, NFC. Le script de sélection valide l'ensemble avant publication, refuse doublons et formats invalides, et utilise une lecture conditionnelle sur l'ETag pour refuser un remplacement concurrent. Il publie les octets sous leur SHA-256. Production conserve exactement le catalogue testé ; elle ne relit jamais le dossier modifiable.

La preuve Test inclut le SHA-256 du catalogue dans son identifiant. Des CSV nouveaux avec le même commit peuvent donc être testés sans conflit avec une ancienne preuve. Le téléchargement historique par commit reste disponible uniquement quand la nouvelle preuve n'existe pas, avec comparaison stricte du catalogue et des images.

## Foundation et conservation

Foundation `9e7e8677-6aa2-4285-b2ed-e302fac9b5c9` : réussie, 49 changements contrôlés. Deux dépôts ECR immuables Fedow/LaBoutik, leurs droits de publication/lecture et ceux du dossier CSV sont appliqués. Une seule nouvelle EC2, `i-0824730d4d46b3673`, a été créée pour `gala-images-csv-2026-10-08`. Le catalogue précédent, les anciennes EC2 et leurs volumes racine sont conservés. Le gala actif et l'EIP restent sur Smoke ; aucun DNS n'est modifié.

Avant release, un contrôle SSM prouve l'absence de conteneur, de base Fedow et de manifeste déployé sur cette nouvelle EC2.

## Pipeline principale et promotion

Test `a6208210-d3d0-4b78-b0b7-2720c28f9a36` : réussie depuis la fusion dans main. Les trois images sont construites et la sélection S3 retrouve les trois lots. Le déploiement Smoke (`c22137f6-42e2-4d2b-9097-d03d9623b52e`) retrouve 7 020 cartes et en crée zéro. La comparaison indépendante avant/après conserve exactement les identités des cartes, les nombres de wallets/tokens/transactions et les soldes par asset.

La release `gala-images-csv-2026-10-08-v1.0.0` reprend les images, leurs bases natives et le catalogue de cette preuve. L'artefact validé par CodeBuild est comparé octet pour octet au manifeste revu, puis son SHA-256 et l'EC2 cible sont vérifiés avant l'approbation de promotion. SHA-256 : `1df5a8933be789a3614c9961ef922813ef80f042e44504247609fd167627e567`.

La pipeline dédiée `95aac80f-ebe6-4883-b611-c364b9b1f936` a réussi son premier déploiement, SSM `0cf66e65-94bb-4db3-b133-84a14ed6a409`. Les huit assets de sources exactes sont publiés et vérifiés sur GitHub avant ce déploiement.

## Vérifications finales

Reçu du premier import automatique, exécuté par la pipeline :

```json
{"status":"ready","expected":7020,"created":7020,"existing":0,"lots":3}
```

- Le contrôle indépendant SSM `e7167168-1d0f-4d72-ab84-8b60e44db2bf` vérifie les 7 020 associations exactes en mode `--check`, zéro création, trois générations et aucune carte réclamée. Les soldes sont à zéro.
- Fedow utilise `django.db.backends.sqlite3`. Sa commande native `import_cards.py` garde son empreinte `cf1217b46eacd7f8e85ef71c6c5e6df79ec6e03baeb422030e38dabc001c30a6`.
- Les quatre images exécutées correspondent au manifeste. Les labels du commit et des bases natives sont contrôlés avant démarrage. Les dix fichiers copiés sont vérifiés indépendamment par SHA-256 dans les conteneurs : SSM `e40bcda0-18a6-414e-8278-19a2b036bce0`. Aucun montage ne couvre ces sources, aucun Python/HTML/CSV n'est monté sur les applications. Les volumes de données, logs, Redis, configurations Nginx et publication des sources restent présents.
- Trois QR, un par lot, ouvrent le bon formulaire de liaison en HTTPS local. Le tenant apex, le domaine de retour de recharge, le bouton de recharge et Celery passent le healthcheck. Aucun formulaire de liaison n'est soumis.
- Les trois routes d'administration répondent 200 avec un formulaire identifiant/mot de passe, y compris `cashless.../admin/`. Les comptes et leurs flags sont vérifiés par l'outil de readiness. Aucune connexion par mot de passe n'est soumise pendant ce test : SSM `a5734af0-58f7-4d71-8857-030c1b4587fd`.
- Le contrôle NFC SSM `8ad4e1f1-ed5e-4352-a369-bf14564fba10` utilise le client natif contre le vrai Fedow du nouveau gala. Les cartes usine blanche et noire sont retrouvées avec les bonnes identités. Une carte inconnue est enregistrée par le validateur, une autre par la vue de scan réelle ; leur répétition conserve les mêmes UUID et ne crée aucun doublon. Les UUID retournés correspondent à ceux du **nouveau** Fedow. Le test laisse deux cartes synthétiques sans QR imprimé, anonymes et sans solde, en plus des 7 020 cartes de stock. Il ne réalise aucune vente ni recharge.
- La sauvegarde automatique initiale `20261008T130009Z` contient les trois bases et les checksums exacts. Sa copie SQLite ouverte en lecture seule a une intégrité `ok`, 7 020 cartes et la répartition 3 510 / 1 755 / 1 755.
- Le drill SSM `aa1280b0-dbf2-414d-9694-ef7388d0111f` restaure les deux dumps PostgreSQL en conteneurs jetables sans réseau, volumes hôte ou ports exposés : 59 tables LaBoutik et 180 Lespass. Il vérifie aussi la restauration de Fedow SQLite. Les cibles temporaires sont supprimées et le healthcheck de l'instance passe ensuite. Les bases du gala ne sont pas remplacées.

## Portée et usage futur

Les contrôles ciblent la nouvelle EC2 via `127.0.0.1` et les hostnames configurés ; ils ne peuvent pas réussir en consultant involontairement Smoke. Le certificat temporaire est accepté pour cette instance inactive, et `DEBUG=1` est limité aux processus shell du test NFC/installation. Les processus web restent dans leur configuration déployée. Cet essai ne prouve pas un nouveau certificat public, un paiement Stripe, une livraison email ou un parcours réalisé avec un lecteur physique. Aucun paiement réel n'est engagé.

Les trois CSV restent dans le dossier S3 pour les prochains galas. Déposer les futurs lots au format natif dans un nouveau sous-dossier de génération, puis lancer Test et promouvoir son catalogue figé. Aucun commit du CSV n'est nécessaire. Déposer ou retirer un fichier ne modifie pas les soldes ou cartes d'un gala déjà démarré.

Les tests locaux livrés sont 137 tests de déploiement (134 réussis, trois contrôles dépendants de Linux ignorés sur Mac), plus 23 régressions cartes/prix/installation/restauration native exécutées dans l'image LaBoutik. Les contrôles de premier démarrage et de restauration décrits ci-dessus constituent les preuves AWS séparées.

Les reçus, plans, artefacts, snapshots privés et résultats SSM sont conservés sous `.context/images-csv-gala-20261008/`.

## Conservation finale

Après les contrôles, une dernière sauvegarde est effectuée et le healthcheck passe. Seule l'EC2 du nouveau gala est arrêtée, avec état AWS `stopped` confirmé. Son volume racine, ses bases (7 020 cartes de stock plus deux cartes synthétiques de test), ses secrets et ses sauvegardes sont conservés. Smoke reste actif sur le domaine commun et l'EIP demeure inchangée. Aucun autre gala n'est arrêté ou remplacé.
