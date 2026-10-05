# Fonctionnalités retirées : retour au code TiBillet

Ce dossier conserve les fonctionnalités retirées et les preuves de leur retour
au comportement TiBillet. Elles ne sont pas réintroduites automatiquement.

La décision utilisateur est de rester le plus proche possible de TiBillet vanilla.
Un rollback reprend le code d'origine de la version concernée ; il ne réimplémente
pas le comportement à partir d'une description.

## Retraits réalisés dans le dépôt

| ID | Personnalisation retirée | Commit de retrait | Documentation |
| --- | --- | --- | --- |
| C | Happy hour et substitution des prix | `4e20db20` | [C-happy-hour.md](C-happy-hour.md) |
| D | Limite de deux terminaux, éviction FIFO et exemption admin | `e27aa554` | [D-limite-terminaux.md](D-limite-terminaux.md) |
| F | Option de désactivation de la synchronisation de monnaie cadeau | `50a6906f` | [F-option-monnaie-cadeau.md](F-option-monnaie-cadeau.md) |
| G | Réparations automatiques et ancienne copie du serializer Fedow | `35cc9918` | [G-reparations-fedow.md](G-reparations-fedow.md) |
| H | Dashboard financier Gala et copies de ses vues, routes et templates | Lot local du 5 octobre 2026 | [H-dashboard-financier](H-dashboard-financier/README.md) |
| I | Backend PostgreSQL de Fedow et élargissement SQL des secrets Stripe | `7f31acd3` | [I-postgresql-fedow](I-postgresql-fedow/README.md) |
| LaBoutik | Écarts hérités des billets, adhésions, carte primaire, doublons et erreurs | Lot local du 5 octobre 2026 après `6c373f10` | [LaBoutik-ecarts-herites](LaBoutik-ecarts-herites/README.md) |

Au moment des premiers retraits, ces modifications étaient locales et non
déployées. Elles sont maintenant poussées sur la branche et validées sur Smoke
puis sur une nouvelle EC2, avec les preuves dans
[l'audit du premier lancement](../../deploy/docs/operations/first-launch-validation-2026-10-05.md).
Aix n'a pas été mise à cette version et les derniers changements ne sont pas
fusionnés dans `main`. Les anciennes données Smoke ont été archivées avant
ses essais sur bases vides ; aucun solde existant n'a été transféré vers SQLite.

## Choix conservés ou en attente

| ID | Décision actuelle |
| --- | --- |
| A | Garder le parcours QR de connexion/liaison/recharge |
| B | Garder le guide de connexion rapide et l'interface d'accueil associée |
| E | Conservé et corrigé : enregistrement uniquement sur carte introuvable, délais réseau TiBillet restaurés |
| G | Retiré : serializer natif de l'image Fedow, sans montage ni copie de remplacement |
| H | Retiré à la demande de l'utilisateur le 5 octobre 2026 ; dashboard natif de l'image, aucun montage de remplacement |
| I | Fedow SQLite natif démarré sur une instance neuve ; PostgreSQL Smoke archivé, sauvegarde mixte et restauration isolée vérifiées : [audit du lancement](../../deploy/docs/operations/first-launch-validation-2026-10-05.md) et [configuration archivée](I-postgresql-fedow/README.md) |
| J | Garder pour l'instant l'installateur reprenable |
| K | Conserver l'offre de sources ; risque de blocage d'un nouveau déploiement documenté séparément |
| L | Décision reportée : ne pas retirer pour le moment |

Les propositions de nouveaux modules/table de sessions du document du 3 octobre
sont historiques. La proposition de conserver D a été abandonnée ; aucune table
de sessions ni nouveau système de limitation n'a été implémenté.

## Méthode de rollback exigée

1. Identifier le composant, le commit d'introduction de la personnalisation, la
   version réellement choisie comme référence et les fonctionnalités à conserver.
2. Utiliser le code TiBillet exact correspondant à l'image épinglée. Pour Lespass,
   utiliser le commit upstream/fork pertinent ; pour Fedow et LaBoutik, utiliser
   le catalogue `deploy/source/image-sources.json`. Ne pas prendre une branche
   `main` mouvante et ne pas copier une ancienne version incompatible avec l'image.
3. Vérifier l'archive upstream par SHA-256 avant d'en extraire les sources.
4. Restaurer les fichiers ou unités concernées en copiant le texte d'origine,
   commentaires et décorateurs compris. Ne pas générer le code avec `ast.unparse`
   et ne pas le réécrire pour reproduire son comportement supposé.
5. Lorsque des fonctions à garder partagent un fichier, expliciter les exceptions
   restantes. Ne pas présenter ce fichier entier comme identique à TiBillet.
6. Vérifier l'identité du texte restauré et le diff restant, puis tester les parcours
   concernés. Un test de comportement seul ne prouve pas l'identité des sources.
7. Conserver un commit ciblé par retrait, les références, la raison et les conditions
   d'une éventuelle réintroduction dans ce dossier.

Les retraits ne constituent pas un revert global de `bc5b1a85`, qui contient toute
l'infrastructure. Ils ne modifient pas les données financières existantes.

## Preuves reproductibles

Référence LaBoutik : `TiBillet/LaBoutik@3fdba313c2dea172bfaa6a06ebab05e1caf62490`.
Archive SHA-256 : `9cb955f13e545b883ca86c65baf73d8ff53b82d1c563d8fe7e8aab0274763dfd`.

[verify-restored-code.py](verify-restored-code.py) compare le texte complet de sept
unités restaurées avec l'archive upstream vérifiée. Il ne normalise pas le texte.
Il vérifie désormais aussi que le client Fedow de LaBoutik n’est plus remplacé
et que les fichiers complets de vues/validation sont natifs hors des deux
exceptions déclarées d’enregistrement des cartes et des notices existantes.
Il vérifie aussi la provenance du serializer et du dashboard Fedow, l'absence de
leurs surcharges G/H et le bloc SQLite natif.
Depuis la racine du dépôt :

```sh
python3 TECH_DOC/features-enlevees/verify-restored-code.py
```

Le script utilise l'archive locale déjà présente dans `.context/source-cache/`.
L'option `--archive` permet d'utiliser une autre copie, à condition que son checksum
soit identique. Le résultat conservé est dans [restoration-receipt.json](restoration-receipt.json).
Le contrôle complémentaire de H est conservé dans son
[reçu du 5 octobre](H-dashboard-financier/restoration-receipt.json).
Le [reçu LaBoutik](LaBoutik-ecarts-herites/restoration-receipt.json) complète ces
preuves après le retrait de ses écarts hérités. Ces contrôles ne vérifient pas
le code d’une instance en service ni l’intégralité des autres réglages applicatifs.

Validation initiale C/D/F : cinq tests locaux de prix/payload terminal, neuf tests de
publication des sources, identité textuelle des cinq unités restaurées, contrôle
des autres fonctions modifiées et syntaxe Python 3.8. Un appel instrumenté confirme
la synchronisation native des deux monnaies avec l'ancienne option à `0` ou `1`.
Cela ne constitue pas un test complet de caisse ou de production.

Validation suivante G/E : huit tests de carte/réseau supplémentaires (22 tests
LaBoutik/publication au total), sept unités restaurées identiques au texte
TiBillet, serializer Fedow sans surcharge et neuf scénarios natifs sur PostgreSQL
local. Les méthodes et limites sont dans les documents G et la suite de l'audit.

## G et I : ce que les sources permettent d'établir

G a été importé depuis nos anciens patches Gala (`a7e496ce`, puis `bc5b1a85`).
La création normale d'un utilisateur TiBillet lui associe déjà un wallet
(`get_or_create_user`) ; un nouvel actif reçoit déjà son FIRST via le signal
`first_block_for_new_asset`. Les deux ajouts G réparent des données incomplètes,
ils ne sont pas requis pour ces chemins nominaux. Leur nécessité sur les données
d'Aix n'est pas vérifiée. La perte d'atomicité portée par cette vieille copie est,
elle, reproduite : voir l'[investigation conservée](../audits/2026-10-03-fork/INVESTIGATION.md).
G est maintenant retiré à la demande de l'utilisateur : son montage et la vieille
copie disparaissent. Le fichier natif de l'image reprend la main ; les nouvelles
vérifications locales sont dans [G-reparations-fedow.md](G-reparations-fedow.md).
La présence éventuelle de données anciennes incomplètes reste à contrôler en
lecture seule avant une promotion de production.

I : nous avons ajouté les copies montées de `settings.py`, pas inventé la
configuration Django. La personnalisation Fedow remplaçait SQLite par
PostgreSQL, ajustait les hôtes/debug
et ajoute un répertoire de templates. LaBoutik utilise déjà PostgreSQL dans sa
référence ; ses différences concernent principalement le répertoire de templates
et les réglages email. Le retrait des montages doit préserver le branchement à la
base existante, sans migration implicite vers une autre base. Le 5 octobre,
l'utilisateur choisit de revenir à SQLite pour Fedow. La configuration PostgreSQL
et ses dépendances sont archivées à l'identique dans
[I-postgresql-fedow](I-postgresql-fedow/README.md). Le dépôt utilise maintenant
le bloc SQLite natif. L’utilisateur choisit ensuite
une base vide, l'ancien PostgreSQL restant conservé. Les anciennes données
Smoke ont ensuite été archivées dans S3 et sur son disque avant les essais
des pipelines ; aucune migration de ces données vers SQLite n'est réalisée.
Le premier lancement et une restauration isolée des sauvegardes mixtes ont
été vérifiés sur AWS. Lespass et LaBoutik conservent leur moteur natif PostgreSQL.

L reste inchangé et sa décision est reportée. La configuration Nginx contient les
routes applicatives et les alias admin ; elle n'est pas une fonctionnalité de
paiement. H est retiré et archivé dans le [dossier H](H-dashboard-financier/README.md) ;
E reçoit seulement une correction limitée de ses
branches d'erreur, sans nouveau module ni modèle. Les décisions et les limites
actualisées de E, I, J, K et H sont dans
[la suite de l'audit](../audits/2026-10-03-suite-G-E-K-H.md), état historique
antérieur au retrait de H.
