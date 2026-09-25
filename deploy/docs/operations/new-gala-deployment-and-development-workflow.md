# Protocole de déploiement d'un gala et de livraison quotidienne

**Statut : architecture cible arrêtée, pas procédure AWS déjà entièrement
opérationnelle.** Voir [l'architecture et les écarts actuels](../ARCHITECTURE-GALAS.md).
Ne pas lancer une création réelle en supposant que les étapes cible existent
déjà dans les pipelines installées.

Ce document décrit deux flux distincts : la création d'un nouveau gala, puis
la livraison normale d'une évolution applicative. Ils ne doivent pas être
confondus : un push applicatif ne crée jamais une EC2, ne modifie jamais le
DNS et ne déploie jamais directement en production.

```text
Nouveau gala
Nom du gala → Foundation (plan contrôlé et apply automatique)
→ EC2 et pipeline Production dédiées → release validée → approbation Production
→ pipeline Gala actif → IP unique → contrôle public

Évolution normale
Branche → PR → main → build et déploiement sur gala-smoke
→ manifeste Production à digests figés → validation → approbation humaine
→ déploiement SSM sur la seule EC2 du gala concerné
```

## Principes non négociables

- Une EC2, des clés générées stables et un préfixe de sauvegarde par gala.
- Stripe test, Stripe live et SMTP utilisent des secrets communs dans Secrets
  Manager ; les droits IAM de Smoke n'autorisent pas la lecture de Stripe live.
- Une seule IP élastique et les mêmes noms publics servent le gala actif.
- Paris (`eu-west-3`) est la seule région runtime autorisée.
- Les secrets ne sont ni dans Git, ni dans Terraform, ni dans CodeBuild.
- Les images de production et les manifestes sont immuables : aucun `latest`.
- Le DNS n'est modifié qu'après une release déployée et vérifiée.
- Une suppression d'ancienne infrastructure n'intervient qu'après validation
  de la remplaçante et restauration testée.

## A. Création d'un nouveau gala

### 1. Nommer le gala et utiliser les paramètres permanents

L'opérateur saisit le **nom du gala** dans Foundation. Celle-ci en dérive un
identifiant technique sûr (*slug*, par exemple `gala-am-aix`) et refuse une
collision avec un autre gala. Si un nom est repris pour une autre édition,
l'opérateur inclut l'édition ou l'année dans le nom saisi.

Ces paramètres sont permanents ou versionnés dans la configuration Foundation ;
ils ne sont pas ressaisis à chaque création :

| Valeur | Exemple | Source |
| --- | --- | --- |
| Domaine apex partagé | `galas-am-aix.rezal.fr` | Configuration commune ; le même pour tous les galas. |
| Plateforme | `v1` | Version standard approuvée de la fondation. |
| Capacité | `t3.medium`, disque 40 GiB | Valeurs standard versionnées, révisables par PR d'infrastructure. |
| Réseau et AMI | VPC, subnet public, AMI approuvée | Configuration commune versionnée ; aucune AMI flottante. |
| Stripe et courrier | Comptes communs | Secrets partagés par usage dans Secrets Manager ; aucune nouvelle saisie par gala. |

Le domaine cible les services suivants :

```text
galas-am-aix.rezal.fr          → Lespass
fedow.galas-am-aix.rezal.fr    → Fedow
cashless.galas-am-aix.rezal.fr → Laboutik
```

### 2. Créer la fondation

1. Vérifier l'identité AWS, le compte Gala et la région.
2. Créer une fois le bucket de state Paris avec
   `infra/terraform-bootstrap/`.
3. Configurer un `backend.hcl` privé pour l'état Terraform du gala.
4. Lancer manuellement la pipeline **Foundation** depuis CodePipeline avec le
   nom du nouveau gala ; un push Git ne la lance jamais.
5. La pipeline vérifie l'identité AWS et ses paramètres permanents, calcule un
   plan et refuse automatiquement les destructions, remplacements ou
   modifications inattendues d'un gala déjà présent. Pour une création
   normale, elle applique sans demander d'approbation manuelle du plan.
6. Attendre **l'exécution CodePipeline complète `Succeeded`** et les contrôles
   détaillés en section C ; la réussite de l'étape Terraform seule ne suffit
   pas. En cas d'échec partiel, corriger le code versionné puis relancer le
   même gala sans réparer son EC2 à la main.

La pipeline AWS installée actuellement demande encore slug, domaine, VPC,
subnet, AMI et capacité, avec une approbation de plan. Elle doit être alignée
sur cette cible **avant** le test de création demandé ici.

Le premier bootstrap de cette pipeline reste une action Terraform manuelle :
une pipeline ne peut pas se créer avant d'exister. Son rôle CodeBuild élevé est
fourni par un administrateur et ne sert qu'à cette pipeline Infrastructure.

La fondation crée notamment :

- EC2 Paris, groupe réseau privé et rôle SSM ; l'IP et l'accès HTTP/HTTPS sont communs au seul gala actif ;
- buckets de state, backups/releases et artefacts ;
- conteneur de clés générées par gala, initialisé une fois après l'apply ;
- secrets d'intégration communs Stripe test, Stripe live et SMTP, à renseigner séparément ;
- ECR Lespass ;
- pipeline Test et CodeBuild ;
- journalisation et politiques IAM minimales.

L'ID réel de l'EC2 doit ensuite être ajouté à
`ops/policy/runtime-allowlist.yaml` et validé avec
`tools/validate-runtime-scope.py`.

### 3. Bootstrap automatique de l'EC2

L'AMI reste une image Ubuntu officielle standard, avec SSM. Elle n'est pas une
« golden AMI » applicative à maintenir.

Au premier démarrage, le bootstrap versionné installe de manière idempotente :

- Docker et Docker Compose v2 ;
- AWS CLI v2 ;
- le dépôt et les scripts runtime ;
- les unités systemd de démarrage et de backup.

Le même installateur doit être rejouable via SSM pour mettre à jour une EC2
existante. Cloud-init lance la première installation, mais ne doit pas être le
seul mécanisme d'upgrade : son user-data est figé au lancement de l'instance.

### 4. Renseigner les intégrations partagées

Foundation crée automatiquement les clés applicatives et mots de passe propres
à chaque gala, une seule fois. Un administrateur renseigne seulement les vrais
identifiants Stripe et SMTP dans les secrets communs. Le format complet et le
chargement des trois fichiers `0600` figurent dans
[Gala actif et secrets partagés](active-gala-and-shared-integrations.md).

### 5. Valider la chaîne Test partagée

Dans la cible, un push sur **`main`** lance la pipeline commune. Celle-ci
construit et contrôle les images nécessaires puis les
déploie **automatiquement sur l'unique EC2 `gala-smoke`**, sans numéro de
release métier ni approbation. Le SHA Git et les digests restent consignés :

```text
sha-<commit Git> → digest sha256:…
```

La pipeline actuelle s'arrête après avoir construit **Lespass seulement** :
ce n'est pas encore un déploiement sur Smoke. Le protocole cible exige le
statut final `Succeeded` et un contrôle de l'application réellement exécutée
sur Smoke. Un build ECR réussi seul ne vaut pas validation du test.
Smoke utilise les clés Stripe **test** du même compte que les clés **live**
des galas réels. Le déploiement Test ne déplace jamais l'IP publique ; la
pipeline « Gala actif » peut néanmoins attribuer volontairement cette IP à
Smoke pour les essais publics de fin de préparation.

### 6. Produire une release immuable

Une release Production est un manifeste revu qui fixe les digests exacts de :

- Lespass depuis l'ECR Gala ;
- Fedow ;
- Laboutik ;
- Traefik.

Le manifeste est conservé sous `releases/<slug>/` et porte un `release_id`
unique, un `fork_commit` (commit applicatif testé) et les quatre références
`image@sha256:…`. Le numéro de release sert à nommer et retrouver la version ;
**il ne prouve pas à lui seul qu'elle a été testée et ne déclenche aucun
déploiement.** Il faut relier chaque digest et le commit applicatif à la
candidate réellement validée sur Smoke. Le commit Git contenant le manifeste
peut être plus récent que le commit applicatif : les deux doivent être visibles
et ne doivent pas être confondus.

### 7. Utiliser la chaîne Production du gala

L'apply Infrastructure crée automatiquement une pipeline Production dédiée au
nouveau gala. Terraform y enregistre l'ID réel de son EC2, son slug et son
document SSM. Une pipeline Aix ne peut donc pas viser l'EC2 d'un autre gala.
Elle comporte obligatoirement une approbation humaine **même lorsqu'un numéro
de release a été attribué**. Le déroulement cible est :

```text
Choix ReleaseManifestPath + commit source Git figé
→ validation du gala, du commit applicatif testé et des 4 digests
→ résumé exact soumis à l'approbateur
→ approbation humaine → déploiement de cet artefact exact par SSM
```

La pipeline CodePipeline est lancée manuellement pour le gala voulu ; son
exécution fixe la révision Git source et le chemin du manifeste. Avant
d'approuver, vérifier l'ID d'exécution, le commit source du manifeste, le
`release_id`, le `fork_commit`, les quatre digests, le résultat du test Smoke
et l'ID de l'EC2 cible. Une nouvelle révision ou un autre manifeste exige une
**nouvelle exécution et une nouvelle approbation**. Le manifeste envoyé à S3
doit être en écriture unique et correspondre octet pour octet à l'artefact
validé ; aucun `latest` ni remplacement silencieux après l'approbation.

**Écart actuel à corriger avant ce test :** la pipeline installée place
`ApprovePromotion` avant la validation automatique effectuée par CodeBuild.
Le code vérifie le format des digests, le slug et la plateforme, mais ne prouve
pas encore que les quatre images correspondent à une candidate testée sur
Smoke. Le protocole cible inverse ces étapes et ajoute cette preuve ; on ne
doit pas présenter le contrôle actuel comme déjà complet. L'écriture unique
de l'objet S3 et l'identité exacte entre l'artefact approuvé et déployé sont
également à faire respecter par le code, pas seulement par cette procédure.

La commande SSM ne vise que l'instance définie par Terraform. Elle vérifie le manifeste,
le secret, l'espace disque et les conditions de backup avant le démarrage des
stacks. Une première mise en ligne exige une décision explicite : elle ne doit
pas contourner le garde-fou de backup initial sans être documentée.

### 8. Ouvrir publiquement le gala

Après un déploiement réussi et des healthchecks valides :

1. lancer manuellement la pipeline distincte **Gala actif** et choisir le
   gala cible (`gala-smoke` ou un gala réel) ; elle vérifie l'EC2 et déplace
   l'unique Elastic IP après
   confirmation. La création Foundation ne fait pas cette sélection ;
2. lors de la première migration seulement, pointer les trois noms DNS vers
   l'IP Paris partagée ;
3. vérifier le certificat TLS et tester Lespass, Fedow et Laboutik depuis
   l'extérieur ;
4. mettre le registre privé du gala à l'état `live`.

Une sauvegarde puis une restauration isolée validée sont requises avant de
supprimer une ancienne cible.
Après cette première migration, les bascules **Production → Smoke → Production**
se font en relançant la pipeline Gala actif avec le nom de la cible ; les noms
DNS ne changent plus. Le gala qui perd l'IP ne reçoit plus de trafic public.
Pour permettre un retour rapide, son EC2 reste en marche par défaut :
« inactif » ne signifie pas « arrêté ».

## B. Flux de développement normal

### Développer et intégrer

1. Créer une branche dédiée à la modification.
2. Lancer les tests pertinents localement.
3. Ouvrir une PR, faire relire puis fusionner dans `main`.
4. La pipeline Test construit la candidate liée au commit de fusion et la
   déploie sur l'unique EC2 Smoke (cible non encore implémentée). Elle ne
   modifie aucune EC2 Production.

Les changements applicatifs ne modifient pas l'infrastructure. Les changements
dans `deploy/`, Terraform, IAM, secret, DNS ou la politique d'allowlist suivent
un plan revu séparé.

### Promouvoir une version

1. Choisir les digests effectivement validés sur Smoke et les dépendances
   exactes, puis composer le manifeste de release.
2. Déclencher manuellement la pipeline Production du gala concerné. La seule
   variable saisissable est le chemin du manifeste ; l'EC2 n'est jamais un
   paramètre utilisateur.
3. Laisser la pipeline valider automatiquement le manifeste et sa provenance.
4. Vérifier le résumé pré-approbation, approuver, puis suivre le preflight,
   le déploiement SSM et les healthchecks.
5. Enregistrer le `release_id` effectivement déployé dans le registre privé.

Un rollback applicatif n'est tenté qu'après avoir vérifié la compatibilité
des données et des migrations. Il consiste alors à promouvoir un manifeste
immuable précédent ; il ne consiste pas à réutiliser `latest` ou à reconstruire
sur l'EC2. Il suit lui aussi l'approbation manuelle Production.

## C. Essai obligatoire de Foundation, effectué et surveillé par l'agent

Ce test est distinct de la pipeline Test applicative. Il sert à prouver que
**Foundation crée vraiment un nouveau gala et sa pipeline Production** depuis
une demande neuve. L'utilisateur autorise l'agent à lancer les exécutions et
à donner l'approbation manuelle Production pendant cet essai ; cela ne dispense
pas de vérifier les prérequis ni de laisser une trace de l'artefact approuvé.

1. Avant le lancement : vérifier le compte AWS et la région, l'état Terraform
   distant, le catalogue des galas, les permissions, la connexion GitHub, les
   secrets communs et le coût/la durée de vie de l'EC2 de démonstration
   **Gala Validation** (`gala-validation`). Les valeurs Stripe/mail
   doivent être présentes avant les essais applicatifs, sans être lues dans
   les logs. Confirmer que la pipeline
   installée correspond bien au code d'architecture validé.
2. Démarrer **soi-même** Foundation depuis CodePipeline. Relever l'ID
   d'exécution et le commit source. Suivre chaque étape jusqu'au statut final
   via CodePipeline, les journaux CodeBuild et les événements Terraform.
3. Après l'apply : vérifier que la nouvelle EC2 seule a été créée (pas de
   remplacement d'Aix ou Smoke), qu'elle est `running` et SSM `Online`, que
   cloud-init a installé les dépendances et les scripts du commit prévu, et
   que ses groupes réseau n'ouvrent pas le gala au public par erreur.
4. Vérifier sans lire les valeurs sensibles que les conteneurs Secrets Manager
   existent, que les clés propres au gala ont une version `AWSCURRENT`, que le
   secrets communs Stripe/SMTP sont référencés avec les droits IAM adaptés,
   et que les préfixes de sauvegarde et permissions IAM sont limités au gala.
5. Vérifier que Foundation a créé la pipeline Production et CodeBuild de ce
   gala, connectés au bon dépôt et à la bonne branche, avec le document SSM
   et **l'ID exact de cette nouvelle EC2**. Vérifier qu'elle ne peut cibler Aix ou
   Smoke. Le résultat final Foundation doit être `Succeeded`.
6. Prouver le parcours applicatif : push sur `main`,
   exécution Test `Succeeded` et code actif sur Smoke ; manifeste lié aux
   digests testés ; validation Production avant approbation ; approbation
   manuelle par l'agent pour l'essai ; déploiement `Succeeded` et healthchecks
   sur la seule nouvelle EC2. Après validation des prérequis de mise en ligne,
   tester la pipeline Gala actif dans les deux sens entre Smoke et Production,
   sans changement DNS entre ces bascules.
7. À chaque échec, conserver l'ID d'exécution et relever **l'étape et la cause
   exactes** dans les logs. Corriger la définition versionnée (Terraform,
   buildspec, bootstrap, installateur ou application), puis relancer le flux
   reproductible pour le même gala. Une commande SSM de diagnostic en lecture
   seule est permise ; installer un paquet, modifier un fichier ou démarrer
   manuellement un service sur l'EC2 n'est pas une correction acceptable.
   Ne conclure qu'après un nouveau succès complet, sans correctif local.
8. Après le test, si l'EC2 de démonstration n'est pas le gala actif, l'arrêter
   pour limiter le coût de calcul et conserver ses ressources pour inspection.
   Ne la supprimer que par un flux Terraform de retrait explicite et vérifié.

## État actuel de l'outillage

Foundation, la pipeline Production manuelle par gala et le build Test Lespass
existent, mais **le parcours cible ci-dessus n'a pas été validé de bout en
bout**. La Test ne déploie pas encore Smoke ; Foundation demande encore des
paramètres techniques et une approbation de plan ; la validation automatique
Production vient encore après l'approbation. Les changements locaux de clés
générées, d'IP partagée et de pipeline Gala actif ne sont pas encore appliqués
dans AWS. Ne pas confondre code préparé et fonctionnalité déployée.

## Références

- [Fondation AWS](../../infra/README.md)
- [Accès AWS](../aws-access.md)
- [Périmètre et portes de changement](../platform/scope-and-change-gates.md)
- [Registre d'un gala](gala-registry.md)
- [Bootstrap de la pipeline Infrastructure](foundation-pipeline-bootstrap.md)
- [Démarrage, arrêt et dormance](start-stop-dormance.md)
- [Sauvegarde et restauration](backup-restore.md)
