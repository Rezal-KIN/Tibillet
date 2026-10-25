# Offre d'accès aux sources des instances Gala

Offre initialement déployée et contrôlée sur Aix le 3 octobre 2026, release
`gala-am-aix-v1.0.8`. À partir de `gala-am-aix-v1.0.10`, les téléchargements
de production sont hébergés dans les Releases GitHub, indépendamment de la VM.
Cette documentation décrit le mécanisme technique et les vérifications réalisées.
Le dépôt public est <https://github.com/Rezal-KIN/Tibillet>, sous GNU AGPLv3.
Les auteurs et dates de modification sont indiqués dans [NOTICE.md](../../../NOTICE.md).
Le nom d’attribution du fork est **AM-Rezal** (pages, crédits et notices corrigés
dans la release `gala-am-aix-v1.0.9`). `Rezal-KIN/Tibillet` reste l’identifiant
technique du dépôt GitHub.

## Audit de la release Aix en service

Lecture seule via SSM, identité AWS vérifiée avant l'audit. Le manifeste sur l'hôte
et les références des conteneurs correspondent à `gala-am-aix-v1.0.7`.
Le checkout des patches utilise le même commit que l'image Lespass :

| Composant | Sources vérifiées | Image |
| --- | --- | --- |
| Lespass | `Rezal-KIN/Tibillet@ff59f523e9ef9589938ef00951848da15bb45224` | `sha256:e65e8bab87a765d94685386e9c95c9a07d27193464e33b50dbd93c1e73f88e6b` |
| Fedow | `TiBillet/Fedow@1668d94fb2391cd1b9fef28abf857c356e13207c` + fichiers montés du fork | `sha256:17951150aba8facf9cc7e9213edf4d3406bde78b9ee17802671684961053be83` |
| Laboutik | `TiBillet/LaBoutik@3fdba313c2dea172bfaa6a06ebab05e1caf62490` + fichiers montés du fork | `sha256:012f3f1a14b532766f6faa9b6dc55ce53b0f2e65de7035066b96e86b30c006e9` |

Comparaison des blobs Git avec les fichiers exécutés : 870 fichiers source
Lespass contrôlés sans écart ; 107 fichiers Fedow et 572 fichiers Laboutik
contrôlés, avec les écarts applicatifs correspondant aux fichiers montés du fork.
Les empreintes SHA-256 de ces mounts ont été relevées. Le script de publication
Docker de Laboutik diffère aussi : `VERSION="1.7"` dans l'image, contre `1.4` dans
le commit original. Cet écart audité est reproduit dans le catalogue des sources.

Cette comparaison couvre les sources Python, HTML, JS, CSS, scripts, dépendances
déclarées et notices principales, pas les octets de tous les assets binaires.
Les différences dans les environnements, logs et répertoires de données sont
exclues. Aucune base, clé ou configuration secrète n'est exportée par l'outil.

Lors de l'audit initial de v1.0.7, l'accueil public de Lespass proposait uniquement
le GitHub officiel, sans accès au fork modifié. La release v1.0.8 ajoute l'offre
visible vers les sources correspondantes.

## Validation et mise en ligne

Candidate applicative et checkout des patches :
`91941740979afecce0b99b4314545664ed4be413`. Image Lespass :
`sha256:207075f72ac6550d3ee597c4990e143d7fd98b158c2165c5e27a48436476731f`.
Les images Fedow, Laboutik et Traefik restent celles du manifeste précédent.

- Test Smoke `f997b1a3-f198-4a4c-b709-eadd571f6bba` : `Succeeded`.
- Manifeste v1.0.8 publié dans Git au commit
  `95d9f03ea6c3a8b56d630e237955f74a0c98af41`, SHA-256
  `7e1826ac6a87e9da89465b72777d1846f33cd815e17f24f8a0a70aece03eafa5`.
- Pipeline Production Aix `5a4c8bda-8f90-4c93-8bce-ba079fc676ea` : validation
  automatique, approbation de l'artefact exact sur demande explicite de
  l'utilisateur, puis déploiement SSM et statut final `Succeeded`.
- Contrôles en HTTPS depuis l'extérieur avec certificats vérifiés : les trois
  accueils présentent le lien, les trois `/source/` retournent 200 sans connexion,
  et les quatre archives sur chaque domaine ont les SHA-256 annoncés.
- Comparaison en lecture seule des archives avec les fichiers exécutés sur Smoke
  puis Aix : 870 sources Lespass, 110 Fedow et 573 Laboutik contrôlées sans fichier
  manquant ni écart ; commits et digests concordent avec le manifeste actif.
- Healthcheck applicatif et Celery réussi ; timer de sauvegarde Aix actif.
  Les 78 tests locaux de déploiement passent. La première candidate avait révélé
  une incompatibilité de chemin dans les settings Laboutik, corrigée et testée
  avant toute promotion Aix.

Accès publics :

- <https://galas-am-aix.rezal.fr/source/>
- <https://fedow.galas-am-aix.rezal.fr/source/>
- <https://cashless.galas-am-aix.rezal.fr/source/>

Ces vérifications prouvent l'accès et la correspondance des sources contrôlées.
Elles ne constituent pas une reconstruction indépendante intégrale des trois
applications, une nouvelle validation de paiement réel ou une conclusion sur
les éventuels manquements historiques.

## Mécanisme préparé

- Lespass conserve les liens et crédits officiels, et ajoute un lien `/source/`
  au pied de page partagé ainsi qu'au menu d'administration.
- Depuis le rollback local du 5 octobre 2026, Fedow conserve le lien dans son
  admin, l'accès `/source/` et l'en-tête HTTP `Link`. Les copies de templates du
  dashboard et de l'accueil public sont retirées : leurs liens de pied de page
  disparaissent. Les constats des releases précédentes ci-dessus restent
  historiques. Voir le [dossier de retrait H](../../../TECH_DOC/features-enlevees/H-dashboard-financier/README.md).
- Laboutik ajoute le lien à la connexion, au kiosque, aux informations de caisse
  et à son admin. Le lien ne donne aucun accès supplémentaire aux données métier.
- Les trois Nginx servent le même répertoire public en lecture seule sous
  `/source/`. L'en-tête `Link` signale aussi cette page aux clients des API.
- Le générateur part exclusivement de commits Git fixes et d'archives originales
  dont les empreintes SHA-256 sont vérifiées. Les overlays sont dérivés du Compose
  de la version des patches, plutôt que d'une liste indépendante susceptible de
  diverger. Les templates d'administration montés en répertoire sont inclus aussi.
- Chaque release fournit quatre archives : Lespass, Fedow modifié, Laboutik modifié,
  et le déploiement. Les notices originales, licences, dépendances verrouillées,
  scripts et instructions sont conservés. Les environnements privés, données et
  historique Git ne sont jamais empaquetés.
- Les archives ont une URL immuable et restent disponibles après les mises à jour.
  Une image inconnue ou une source absente bloque la génération avant le démarrage
  des nouveaux conteneurs. Le nouvel index est activé seulement après leur
  healthcheck, puis son accès HTTP est vérifié sur les trois domaines.

## Hébergement indépendant du serveur du gala

Les archives de production sont hébergées dans les [Releases GitHub](https://github.com/Rezal-KIN/Tibillet/releases).
Le serveur du gala peut être arrêté sans couper ces téléchargements. La page
`/source/` reste un sommaire accessible lorsque le site fonctionne ; ses huit
liens de téléchargement pointent directement vers GitHub. La Release peut aussi
être partagée directement, sans passer par le domaine AWS.

Après validation Smoke, préparer le manifeste de production depuis ses images
et son commit exacts, puis publier les sources **avant** la promotion :

```sh
python3 deploy/tools/build-source-offer.py \
  --repository . --manifest releases/gala-am-aix/<release>.json \
  --catalog deploy/source/image-sources.json \
  --deployment-commit <commit-applicatif-complet-validé-sur-Smoke> \
  --output .context/sources-github --cache .context/source-cache
python3 deploy/tools/publish-source-release.py \
  .context/sources-github/releases/<release>-<commit-sur-12-caractères>
```

La publication nécessite une connexion locale `gh` au dépôt ; aucun identifiant
GitHub n’est installé sur la VM. Le script publie uniquement les huit fichiers
préparés, vérifie leurs empreintes, puis rend la Release publique. Il refuse de
remplacer des fichiers existants par des octets différents.

La production utilise `--github-release` : les huit assets publics doivent avoir
les mêmes empreintes que les sources générées depuis les commits déployés. Sinon,
le déploiement s’arrête avant le démarrage de la nouvelle version. Smoke conserve
son offre locale pour pouvoir vérifier une candidate avant sa publication.
Les instructions de reconstruction proviennent aussi du commit du déploiement,
afin de conserver des archives identiques entre préparation et production.

## Génération et contrôle

Depuis la racine du dépôt, avec Python 3.10 ou supérieur et Git :

```sh
python3 deploy/tools/build-source-offer.py \
  --repository . \
  --manifest releases/gala-am-aix/gala-am-aix-v1.0.7.json \
  --catalog deploy/source/image-sources.json \
  --deployment-commit ff59f523e9ef9589938ef00951848da15bb45224 \
  --output .context/offre-sources-aix-v1.0.7 \
  --cache .context/source-cache
```

Ce mode prépare les sources de la version auditée, sans les publier sur l'hôte.
Pour une nouvelle release, utiliser son manifeste et le commit des patches qui
sera déployé. Le processus normal dans `deploy-release.sh` l'effectue avant le
lancement de la stack. Le cache local évite des téléchargements répétés ; chaque
archive originale est vérifiée même en cache. Une nouvelle image Fedow/Laboutik
nécessite un nouvel audit et une actualisation du catalogue.

Après promotion, vérifier sans authentification :

1. `/source/` sur les trois domaines, accessible sans paiement ; vérifier les
   liens visibles conservés (Lespass, LaBoutik et administration Fedow) ainsi
   que l'en-tête `Link` de Fedow. Son dashboard natif n'a plus notre lien visible
   de pied de page. Ce contrôle décrit l'accès technique, sans conclure à la
   suffisance juridique de cette visibilité.
2. Télécharger les quatre archives, `SHA256SUMS` et `source-manifest.json` ; vérifier
   les empreintes et la concordance avec la release en service.
3. Contrôler que les fichiers montés correspondent aux overlays annoncés et que
   les sources de Lespass correspondent au commit qui a construit l'image.
4. Vérifier la reconstruction avec les instructions [BUILD.md](../../source/BUILD.md).
   Les tests du générateur et de Nginx ne constituent pas une reconstruction
   complète des trois applications ou une validation de paiement.

## Notices tierces et limites de l'audit

Notices retrouvées et conservées : auteurs TiBillet (`AUTHORS.md`), template
Dimension HTML5 UP et CC BY 3.0, Luciole et CC BY 4.0 dans `Read Me.txt`, polices
Playwrite IS et Staatliches et SIL OFL dans leurs `OFL.txt`, notices incluses dans
les sources JS/CSS et dépendances verrouillées par Poetry.

Cet inventaire ne certifie pas la provenance de toutes les images utilisateur,
ni toutes les licences transitives Python/JS et dépendances système. Les exceptions
et notices des composants tiers restent applicables ; les archives ne les
relicencient pas uniformément sous AGPL.

Le traitement d'éventuels manquements historiques et d'accords séparés est distinct
de cette correction technique. Les textes de référence sont les articles 1, 4, 5,
8 et 13 de [l'AGPLv3](https://www.gnu.org/licenses/agpl-3.0.en.html).
