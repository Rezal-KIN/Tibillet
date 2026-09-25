# Architecture cible des galas

Statut : **décisions de conception arrêtées le 25 septembre 2026 ; mise en
œuvre non terminée**. Ce document est la référence pour modifier les
pipelines. La cible décrite ici ne doit pas être présentée comme déjà déployée
dans AWS. Aucun échec ne doit être masqué par une correction manuelle sur une
EC2.

## 1. Vue d'ensemble

Il n'y a qu'un gala public à la fois, au même endroit et avec les mêmes noms
DNS, environ trois fois par an. Les galas doivent néanmoins conserver chacun
leur EC2, leurs données, leurs clés et leur pipeline de production. Une seule
EC2 `gala-smoke` sert aux essais entre les galas ; ce n'est **pas** une EC2 de
test supplémentaire pour chaque gala.

```text
                           ┌──────────────────────────────┐
GitHub, push sur main ───────▶│ Pipeline Test partagée       │
                           │ build + déploiement auto     │
                           └──────────────┬───────────────┘
                                          │
                                          ▼
                                    EC2 gala-smoke

Nom du gala ─▶ Pipeline Foundation permanente ─▶ EC2 gala-X
                                           └──▶ Pipeline Production gala-X

Images validées en test + manifeste figé + approbation manuelle
             ─▶ Pipeline Production gala-X ─▶ EC2 gala-X

Choix du gala public ─▶ Pipeline Gala actif ─▶ IP sur gala-X ou gala-smoke
```

La pipeline Foundation, la pipeline Test et la pipeline de bascule du gala actif
sont communes. Foundation crée **une pipeline Production par gala réel**, avec
un rôle AWS limité à l'EC2 de ce gala. La pipeline Test ne crée pas une
nouvelle EC2 à chaque push.

## 2. Ce qui est décidé

### Création d'un gala

1. Un opérateur lance manuellement la pipeline Foundation et saisit **le nom
   du nouveau gala**. Le *slug* est simplement son identifiant technique sûr
   pour les noms AWS (par exemple `gala-am-aix`) : la pipeline le déduit du nom
   et vérifie qu'il ne désigne pas déjà un autre gala. Le nom de domaine public
   est commun et ne se choisit pas à chaque création. Deux éditions ne peuvent
   pas porter le même identifiant : si un nom est repris, l'opérateur précise
   l'édition ou l'année dans **le nom saisi**, sans slug supplémentaire à saisir.
2. La région, le réseau, l'AMI, la taille standard de l'EC2 et les autres
   paramètres techniques viennent d'une configuration Foundation versionnée,
   pas de questions répétées à l'opérateur. Les identifiants Stripe et e-mail
   sont déjà dans les secrets communs : aucun nouveau secret externe n'est
   demandé pour chaque gala.
3. Foundation valide le nom et sa configuration, puis calcule et applique
   automatiquement le plan Terraform. **Aucune approbation manuelle du plan
   n'est demandée pour une création normale.** Un contrôle automatique refuse
   une suppression ou un remplacement inattendu ; une migration exceptionnelle
   suit un changement de code séparé et revu.
4. Foundation doit garder dans son état la liste des galas déjà créés. Cette
   conservation est technique : si elle ne transmettait que le nouveau gala
   à Terraform, celui-ci pourrait vouloir supprimer les anciens. Elle ne
   signifie pas qu'on redéploie ou modifie les autres EC2 à chaque création.
5. L'apply crée l'EC2 du gala, ses ressources isolées et **sa pipeline
   Production**, connectée au dépôt GitHub par CodeConnections/CodeStar.
6. La pipeline initialise une seule fois les clés applicatives et mots de
   passe propres au gala dans Secrets Manager. Elle doit les conserver lors
   d'un nouvel essai ; notamment, aucune clé Fernet n'est régénérée pour une
   base déjà utilisée.
7. La création ne rend pas le gala public et ne déploie pas automatiquement
   la dernière image sur son EC2.

La création doit être **relançable après un échec partiel avec le même slug**.
Les ressources déjà créées sont reprises ou réconciliées par le code de la
pipeline ; on ne répare pas l'EC2 à la main et on ne crée pas un nouveau slug
pour contourner l'échec. Cette propriété est une exigence cible, pas une
capacité déjà vérifiée de la Foundation actuelle.

### Test partagé et continu

- `gala-smoke` est l'unique EC2 de test partagée. Un push sur **`main`** lance
  automatiquement la pipeline Test.
- La pipeline construit les images nécessaires, effectue ses vérifications,
  puis déploie automatiquement sur **cette EC2 et aucune autre**. Si le build
  ou le contrôle échoue, l'exécution est en échec ; elle ne doit pas annoncer
  un déploiement réussi.
- Le test ne demande ni numéro de release métier, ni manifeste de promotion
  revu, ni approbation humaine. Le SHA Git et les digests d'images restent
  indispensables comme identifiants techniques : ils indiquent précisément
  quel code a été testé, sans recourir à `latest`.
- Le déploiement de test est automatique ; il ne déclenche **jamais** un
  déploiement Production ni une bascule de l'IP publique.
- À chaque push `main`, Test prend le **commit exact du dépôt**, construit
  Lespass et déploie la stack complète sur Smoke. Fedow, Laboutik et Traefik
  utilisent des images figées par digest dans une configuration versionnée ;
  on ne les reconstruit pas inutilement à chaque push. Un changement de leur
  image passe par une modification de ces digests dans Git. Les fichiers de
  configuration et correctifs Fedow/Laboutik présents dans ce dépôt suivent
  également le même commit sur Smoke. La pipeline doit vérifier la cohérence
  de l'ensemble, pas seulement la réussite du build Lespass.
- Si ce déploiement échoue, la pipeline est en échec et la candidate ne peut
  pas être promue. Elle conserve la référence au dernier état sain et les
  journaux du défaut. **Pas de rollback automatique des applications** après
  un échec : une migration de base pourrait rendre les anciennes images
  incompatibles. La correction est versionnée puis redéployée par la pipeline ;
  un retour à une version antérieure n'est exécuté qu'après vérification de
  sa compatibilité avec les données. Ce choix ne concerne pas le rollback de
  l'IP publique, qui reste automatique si une bascule réseau échoue.
- Smoke utilise les **clés Stripe de test du même compte Stripe**. Les galas
  réels utilisent les clés live de ce compte. Ces deux jeux de clés sont dans
  **deux secrets Secrets Manager communs distincts**, avec accès IAM séparés :
  Smoke ne doit pas pouvoir lire les clés live. La sélection dépend de
  l'instance cible et ne demande aucun secret à saisir à chaque gala ; le
  schéma préparé actuellement ne gère pas encore cette séparation.
- Le **même compte SMTP** est conservé, mais Smoke ne doit jamais envoyer de
  vrais messages à des participants : ses destinataires sortants sont limités
  à une adresse de test configurée avec le secret SMTP commun. Aucun nouveau
  compte mail n'est demandé pour chaque gala. Dans la première mise en œuvre,
  l'envoi Smoke est désactivé (backend « dummy » et egress SMTP bloqué) ; un
  relais qui réécrit **tous** les destinataires vers la boîte de test reste à
  réaliser avant de prétendre tester l'envoi effectif d'e-mails.

### Production d'un gala

- La pipeline Production de `gala-X` est créée par Foundation et ne peut
  cibler que l'EC2 de `gala-X`.
- Une modification GitHub seule ne met **pas** cette EC2 à jour. Sa source
  GitHub/CodeConnections fournit une révision précise lors d'un lancement
  manuel avec le chemin du manifeste de release. Celui-ci choisit des images
  par digest pour ce gala. La pipeline vérifie le manifeste, attend une
  **approbation manuelle**, puis déploie exactement ces images via SSM.
- Le `release_id` est une étiquette lisible, **pas** une autorisation de
  déployer. L'approbateur doit voir le commit Git qui contient le manifeste,
  le commit applicatif testé (`fork_commit`) et les quatre digests d'images.
  La validation automatique de ces éléments doit précéder l'approbation ;
  l'artefact approuvé doit être celui effectivement déployé.
- Pour le test de bout en bout de cette architecture, l'utilisateur autorise
  l'agent à donner cette approbation manuelle après avoir vérifié le plan et
  les prérequis. Cette autorisation ne supprime pas l'étape d'approbation.
- Une image testée peut ainsi devenir une release Production sans reconstruire
  silencieusement un autre code.

### Domaines, IP et secrets

- Les noms publics sont identiques pour tous les galas :
  `galas-am-aix.rezal.fr` (Lespass), `fedow.galas-am-aix.rezal.fr` et
  `cashless.galas-am-aix.rezal.fr`. Un seul gala détient le trafic public.
- **Le choix de l'instance publique se fait dans CodePipeline, en lançant
  manuellement la pipeline distincte « Gala actif ».** L'opérateur indique
  le gala cible parmi ceux déjà créés. La pipeline vérifie le choix, affiche
  l'EC2 actuelle et l'EC2 cible, demande confirmation pour cette bascule
  publique, effectue les contrôles, déplace l'unique Elastic IP et inscrit le
  gala actif dans SSM Parameter Store. Ce paramètre enregistre le résultat ;
  on ne le modifie pas à la main. Foundation ne choisit pas automatiquement le
  gala actif lors de sa création.
- `gala-smoke` est aussi un choix possible. Pour les essais finaux proches
  d'un gala, l'opérateur doit pouvoir basculer **l'IP fixe elle-même** vers
  Smoke, puis la remettre sur l'EC2 Production. Les trois noms DNS restent
  identiques et ne sont pas modifiés à chaque bascule. Les autres galas sont
  alors *inactifs publiquement* : ils ne reçoivent ni cette IP ni le trafic
  entrant, mais leur EC2 n'est pas arrêtée par défaut, afin de permettre une
  bascule rapide. Chaque bascule exige contrôle de santé, confirmation et
  retour arrière si la cible échoue.
- La bascule vers Smoke coupe l'accès public au gala Production pendant toute
  sa durée. Elle est donc lancée volontairement dans une fenêtre sans
  transactions réelles ; un push `main` ne déplace jamais l'IP à lui seul.
- Dans le code actuellement préparé, le choix est saisi dans la variable
  `TargetGalaSlug` au lancement de `...-active-gala` : c'est un champ texte
  validé contre le catalogue des galas, **pas** une liste déroulante. La
  pipeline et ce mécanisme ne sont pas encore déployés dans AWS.
- Le DNS doit être dirigé une fois de l'ancienne installation Stockholm vers
  cette IP fixe. Les bascules suivantes ne nécessitent pas de modification DNS.
- Le compte Stripe, le compte courrier et les noms publics sont communs. Les
  identifiants externes résident dans des secrets Secrets Manager communs
  (Stripe test, Stripe live et SMTP), non dans un secret par gala. Les clés
  applicatives, mots de passe des bases et données restent propres à chaque
  gala. Aucune valeur secrète n'est mise dans Git, Terraform ou les journaux
  CodeBuild.
- L'ancienne chaîne Stockholm/Bapts n'est supprimée qu'après validation du
  remplacement, y compris restauration, déploiement et accès public.

## 3. État réel au moment de ce cadrage

| Élément | Aujourd'hui | Cible retenue |
| --- | --- | --- |
| Foundation | Existe et demande aujourd'hui slug, domaine, taille, VPC, subnet et AMI ; elle exige une approbation du plan. Un slug déjà présent est rejeté. | Un nom de gala à saisir ; configuration technique permanente, contrôles automatiques, création sans approbation de plan et reprise sûre après échec partiel. |
| Test | Se déclenche sur un push de `main` et publie une image **Lespass** dans ECR. Il ne déploie pas `gala-smoke`. | Push `main` → build, contrôles et déploiement automatique sur l'unique EC2 `gala-smoke`, avec clés Stripe de test. |
| `gala-smoke` | EC2 distincte gérée par Terraform ; elle n'est pas alimentée automatiquement par la pipeline Test. | Environnement de test continu partagé. |
| Production par gala | Pipeline ciblant une seule EC2, lancée manuellement avec manifeste et approbation. Actuellement, l'approbation précède la validation automatique du manifeste. | Valider et afficher commit, release et digests **avant** l'approbation, puis déployer le même artefact. |
| IP et secrets partagés | Changements de code préparés localement mais non appliqués dans AWS ; le catalogue Smoke contient encore son ancien nom de test et les trois nouveaux secrets externes n'ont pas encore de valeur. | Une IP fixe basculable dans les deux sens entre Smoke et Production, mêmes noms DNS, clés Stripe test/live du même compte. |

Un `terraform validate`, un plan local ou la réussite d'un build Test ne
prouvent ni que l'application tourne sur une EC2, ni que la pipeline complète
réussit. Le critère est le statut final `Succeeded` **et** les contrôles de
l'EC2 cible, sans intervention manuelle corrective sur celle-ci.

## 4. Comment prouver que le parcours est reproductible

1. Utiliser ce document comme contrat de conception, puis aligner le code
   avant toute exécution réelle.
2. Modifier les définitions versionnées (Terraform, buildspecs, bootstrap et
   scripts) puis vérifier localement les tests et le plan exact. Une mise à
   niveau initiale de la Foundation déjà existante doit être distinguée du
   test de création d'un nouveau gala ; on ne prétend pas qu'elle s'est créée
   elle-même.
3. L'agent lance lui-même Foundation avec le nom **Gala Validation** (identifiant
   technique dérivé `gala-validation`) et surveille chaque étape, les journaux
   CodeBuild et le statut
   final, sans approbation manuelle du plan de création. Il vérifie l'EC2,
   son bootstrap, SSM, les secrets techniques initialisés, la pipeline
   Production créée et son ciblage IAM. Une réussite Terraform seule ne
   suffit pas.
4. Faire un push sur `main` ; constater que la pipeline Test
   construit et déploie réellement sur `gala-smoke`, puis contrôle le code
   en cours d'exécution.
5. Préparer un manifeste avec les digests testés, lancer la pipeline Production
   du gala de démonstration, approuver et vérifier le déploiement sur **sa**
   seule EC2. Aucun autre gala ne doit être affecté.
6. Si une étape échoue : examiner la cause dans l'exécution, corriger la
   définition ou le bootstrap versionné, puis relancer le parcours prévu.
   Une commande SSM de diagnostic en lecture seule est possible ; une
   installation ou configuration « à la main » sur l'EC2 ne vaut pas correctif.
7. Une fois les prérequis publics validés, tester aussi la bascule de l'IP
   Production → Smoke → Production avec les mêmes noms DNS, sans modification
   DNS entre ces deux mouvements. La toute première migration depuis
   Stockholm reste distincte. Ne nettoyer l'ancienne chaîne qu'après cela.

## 5. Décisions sur les anciens points incertains

| Point | Décision et raison |
| --- | --- |
| 1 — Branche | `main` après fusion : un push de branche de fonctionnalité ne déploie pas Smoke. |
| 2 — Images Test | Lespass est construit depuis le commit `main` ; Fedow, Laboutik et Traefik sont épinglés par digest et la stack entière est déployée sur Smoke. On met leur digest à jour dans Git lorsqu'on change leur version. Cela rend le test reproductible sans reconstruire des dépendances inchangées. |
| 3 — Même domaine | Smoke et Production servent les **mêmes** noms ; la pipeline Gala actif déplace l'unique Elastic IP dans les deux sens. Le gala non sélectionné est hors trafic public, mais son EC2 reste allumée pour permettre une bascule rapide. |
| 4 — Stripe Test | Smoke utilise les clés test, les galas réels les clés live, dans le même compte Stripe. Les secrets test/live et leurs droits IAM sont séparés ; SMTP reste commun, avec destinataires de Smoke limités à une boîte de test. |
| 5 — Échec Test | La pipeline devient rouge et la candidate n'est pas promue. Pas de rollback applicatif aveugle à cause des migrations de base ; correction dans Git et nouveau déploiement par pipeline. |
| 6 — Essai Foundation | Créer une **nouvelle** EC2 via Foundation sous le nom « Gala Validation » : Aix et Smoke existent déjà et ne prouvent pas une création à partir de zéro. Après l'essai, arrêter cette EC2 si elle n'est pas active ; ne la supprimer que par un retrait Terraform explicite. |

## 6. Pré-requis avant de construire et de lancer

- Aligner Foundation sur une entrée « nom du gala », des paramètres permanents,
  un plan contrôlé automatiquement et une reprise idempotente avec le même
  identifiant après échec partiel.
- Étendre Test jusqu'au déploiement et au contrôle de la stack complète sur
  Smoke, avec le commit exact de `main` et sans déplacer l'IP publique.
- Prévoir dans Secrets Manager les secrets communs Stripe **test et live** du
  même compte avec des droits IAM distincts, ainsi que le secret SMTP commun
  et une adresse destinataire réservée aux e-mails Smoke, sans exposer leurs
  valeurs dans les journaux ou le state Terraform.
- Placer la validation du manifeste, de sa provenance et des digests **avant**
  l'approbation Production, puis déployer l'artefact approuvé sans remplacement.
- Installer et tester la pipeline Gala actif pour Smoke comme pour chaque
  gala réel. La première migration DNS depuis Stockholm reste une opération
  distincte ; aucune suppression de l'ancienne chaîne avant le succès complet.
- Vérifier identité AWS, catalogue, state, coûts et prérequis applicatifs avant
  de lancer Gala Validation. Suivre toutes les exécutions et corriger le code
  versionné, jamais une seule EC2 à la main.
