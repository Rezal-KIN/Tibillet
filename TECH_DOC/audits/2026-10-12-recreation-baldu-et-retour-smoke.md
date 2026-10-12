# Recréation de BalduBapts2026 et retour sur Smoke

Le 12 octobre 2026, l'ancienne instance de préparation Aix a été supprimée à la
demande de l'utilisateur. BalduBapts2026 a été créé sur une EC2 et un disque
neufs par Foundation, puis installé par sa pipeline Production. Le choix final
de l'utilisateur est de laisser **Smoke avec Stripe TEST** sur les domaines
publics. BalduBapts2026 conserve la configuration LIVE standard d'un gala.

## Suppression de l'ancienne instance Aix

L'EC2 `i-0801aa8a2273838aa` est terminée et son volume racine
`vol-0e3b43551b233afce` a été supprimé. La sauvegarde native
`20261012T143451Z` a été restaurée isolément avant la suppression : 59 tables
LaBoutik, 1 620 tables Lespass et intégrité de Fedow SQLite vérifiées.
Le snapshot chiffré complet `snap-00476ed7f724a5d4d` est terminé et conservé.
Les sauvegardes historiques et les secrets de restauration sont conservés.

Le catalogue Foundation garde `gala-am-aix` avec `create_instance: false`.
Sa pipeline Production, ses deux projets CodeBuild, son document SSM et leurs
ressources IAM et journaux dédiés ont été retirés. Le nouvel apply Foundation
a réconcilié l'état sans recréer Aix. Aucun mécanisme général de suppression
n'a été ajouté au code.

## Correction minimale de Foundation

Le premier essai de création de BalduBapts2026 a révélé trois filtres IAM qui
n'autorisaient que les noms de rôles EC2 contenant le préfixe `gala-`.
La [PR 113](https://github.com/Rezal-KIN/Tibillet/pull/113) reprend le périmètre
du projet pour accepter tous les noms de gala validés. Le plan de maintenance
ne change que cette politique ; les actions IAM et les conditions restent
identiques. La simulation autorise BalduBapts2026 et Smoke et refuse un projet
extérieur ainsi qu'un rôle administrateur du projet.

Le commit applicatif testé est `f8e4db76b39c88e4123d9020f1c07e07b91cfdbc`.
Cette correction ne modifie aucun code métier TiBillet.

## Création et première livraison

| Étape | Exécution | Résultat |
| --- | --- | --- |
| Test sur Smoke | `ebfa6837-c142-4bfc-882c-ca5cd13b508d` | Réussi, images construites et déployées |
| Foundation | `61c79d54-d7cd-41f4-bb88-c3bd5dd87330` | Réussi, seule la nouvelle EC2 est créée |
| Production BalduBapts2026 | `b20c6229-6794-4a76-b57c-322f3290659d` | Réussi, premier déploiement SSM en 10 min 56 s |

La nouvelle cible est `i-0b1c966b50fd97f80`, avec un disque chiffré neuf de
40 Gio, SSM Online et une protection contre la suppression. Le manifeste
[`production.json`](../../../releases/baldubapts2026/production.json)
fixe les quatre digests, le commit applicatif, la provenance des images et les
trois lots testés. La validation puis l'approbation portent sur les octets
exacts du manifeste, empreinte
`0f5065a6a31f4354aebe7fd5c5bde5b9c696061939c617ecde8b04003a09bede`.
Le premier lancement automatique de la pipeline créée par Foundation a échoué
avant déploiement, car ce premier manifeste n'existait pas encore sur `main`.
L'exécution explicite ci-dessus utilise le manifeste validé du commit
`d15cae85698626290233a56f539c60cf9fa10202`.

La commande de livraison SSM `7e7d3b2c-1f50-4faf-9adb-288597635368` a réussi.
La nouvelle EC2 n'a reçu aucune réparation manuelle, installation ou modification
de base hors pipeline. Les [sources correspondantes de la release](https://github.com/Rezal-KIN/Tibillet/releases/tag/sources-baldubapts2026-native-20261012-v1-f8e4db76b39c)
sont publiées avec les huit fichiers contrôlés.

## État initial vérifié sur BalduBapts2026

| Contrôle | Résultat |
| --- | --- |
| Cartes importées automatiquement depuis les trois lots S3 | 7 020, dont 3 510 G1, 1 755 blanches et 1 755 noires |
| Vérification complète des associations par l'importeur | 7 020 existantes, 0 ajoutée |
| Cartes associées à un porteur ou portefeuille éphémère | 0 |
| Soldes de tokens positifs | 0 |
| Checkouts et transactions de paiement Stripe | 0 |
| Ventes LaBoutik | 0 |
| Administrations Fedow, LaBoutik et Lespass | Compte commun prêt dans les trois bases |
| Images exécutées | Digests identiques à ceux du Test Smoke réussi |
| Fedow | SQLite natif, aucune variable PostgreSQL résiduelle |
| Lespass et LaBoutik | PostgreSQL natifs |
| Montage de code applicatif ou de CSV | Aucun |
| Pages locales et cinq feuilles de style Lespass | HTTP 200 |
| Worker Celery et connexions locales | Contrôles réussis |
| Unité de démarrage et timer de sauvegarde | Activés et actifs |

Le contrôle SSM `23fcf269-626b-4e44-87a9-5465a6bc127b` a réussi. La sauvegarde
initiale `20261012T203440Z` est restaurée dans des bases isolées : 59 tables
LaBoutik, 180 tables Lespass et vérification SQLite Fedow réussies.

Les montages de données, médias, logs, configurations Nginx et certificats
restent présents. L'offre de sources reste montée en lecture seule sur les
trois Nginx. Ces montages ne remplacent aucun fichier Python, HTML ou CSV
applicatif. L'inventaire détaillé des destinations est conservé dans les preuves
privées de cette recette et les audits antérieurs restent valables pour leur rôle.

## Bascule publique et retour demandé

La pipeline Gala actif a réussi la bascule Smoke vers BalduBapts2026, exécution
`0ba8de93-5479-4a14-85e6-ef3f4db5860d`. Les trois domaines, leurs pages de
sources et les cinq feuilles de style passent onze contrôles HTTPS stricts.
Les sept appels HTTPS des quatre clients applicatifs passent également avec
vérification TLS normale, commande SSM
`906a4d6a-5add-4a90-aa82-71e8b0ba3ca6`.

Le retour vers Smoke a réussi par l'exécution
`028d1f2f-7f44-4076-bb0a-f714c2546ab5`. L'EIP `51.44.90.200` est portée par
`i-0037b98572fccdff2` et le paramètre `/tibillet-gala-paris/active-gala` vaut
`gala-smoke`. Seule Smoke a le groupe de sécurité public ; BalduBapts2026 reste
en marche et inactif. Le DNS n'a pas changé.

Après le retour, les onze contrôles publics et les sept appels HTTPS entre
applications réussissent aussi sur Smoke. La commande SSM de ces appels est
`ae92ac17-4ba5-41c9-940c-6f3b4788a313`. Le contrôle complet du runtime et du
stock de Smoke réussit, commande `76f2be79-e444-4c4e-b12b-4e4e6a777c55` :
Stripe TEST, images exactes du Test, 7 020 associations, aucun ajout,
worker responsive et unités actives. Les deux instances ont les mêmes images,
lots et destinations de montage. Les données Smoke n'ont pas été réinitialisées
pendant cette recréation.

Les [preuves assainies](2026-10-12-recreation-baldu-preuves.json) conservent les
références des pipelines, sauvegardes, commandes SSM et montages observés.
Les journaux complets et les fichiers privés restent sous
`.context/recreation-aix-20261012/`, hors Git. Les dix tests locaux ciblés du
manifeste et du périmètre runtime passent. La clôture ne change que le manifeste,
la cible de l'allowlist et les preuves ; le Test automatique déclenché par cette
fusion sera arrêté avant DeploySmoke pour conserver les images communes validées.

## Essais utilisateur restants

Cette recette valide l'installation, les associations de cartes, les services,
les sauvegardes et le routage. Le parcours physique carte et terminal, la
recharge Stripe TEST puis son retour sur le site restent à refaire sur Smoke.
Smoke neutralise les emails sortants ; la réception de l'invitation native du
nouveau gala reste à confirmer séparément. L'aspect visuel n'a pas été contrôlé
dans un navigateur, bien que les CSS répondent correctement. Aucun paiement
réel n'a été exécuté.
