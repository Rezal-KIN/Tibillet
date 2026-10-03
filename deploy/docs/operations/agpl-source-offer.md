# Offre d'accès aux sources des instances Gala

État de préparation au 3 octobre 2026. Cette documentation décrit le mécanisme
technique ; la présence des fichiers dans Git ne prouve pas leur déploiement.
Le dépôt public est <https://github.com/Rezal-KIN/Tibillet>, sous GNU AGPLv3.
Les auteurs et dates de modification sont indiqués dans [NOTICE.md](../../../NOTICE.md).

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

L'accueil public de Lespass possède actuellement un lien vers le GitHub officiel,
sans accès au fork modifié. L'offre visible n'est corrigée qu'après promotion de
la release contenant les changements de cette PR.

## Mécanisme préparé

- Lespass conserve les liens et crédits officiels, et ajoute un lien `/source/`
  au pied de page partagé ainsi qu'au menu d'administration.
- Fedow ajoute le lien à son template partagé, à son accueil public et à son admin.
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

1. `/source/` sur les trois domaines, accessible sans paiement et avec un lien
   visible depuis les écrans utilisés (publics et administratifs).
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
