# Déployer un nouveau gala et livrer au quotidien

Ce document décrit deux flux distincts : la création d'un nouveau gala, puis
la livraison normale d'une évolution applicative. Ils ne doivent pas être
confondus : un push applicatif ne crée jamais une EC2, ne modifie jamais le
DNS et ne déploie jamais directement en production.

```text
Nouveau gala
Décision métier → plan Terraform → fondation AWS → secret runtime
→ build Test → release immuable → approbation Production → DNS → contrôle

Évolution normale
Branche → PR → main → build Test/ECR → manifeste de release
→ approbation humaine → déploiement SSM exact
```

## Principes non négociables

- Une EC2, un secret runtime et un préfixe de sauvegarde par gala.
- Paris (`eu-west-3`) est la seule région runtime autorisée.
- Les secrets ne sont ni dans Git, ni dans Terraform, ni dans CodeBuild.
- Les images de production et les manifestes sont immuables : aucun `latest`.
- Le DNS n'est modifié qu'après une release déployée et vérifiée.
- Une suppression d'ancienne infrastructure n'intervient qu'après validation
  de la remplaçante et restauration testée.

## A. Création d'un nouveau gala

### 1. Figer les décisions métier

Avant toute commande AWS, confirmer et enregistrer :

| Valeur | Exemple | Rôle |
| --- | --- | --- |
| Slug stable | `gala-am-aix` | Identifie toutes les ressources techniques. Ce n'est pas un domaine ni une année. |
| Domaine apex | `galas-am-aix.rezal.fr` | Domaine Lespass ; Fedow et Laboutik utilisent leurs sous-domaines. |
| Plateforme | `v1`, `v2-preview` ou `v2` | Ne change pas silencieusement en cours de gala. |
| Capacité | `t3.medium`, disque 40 GiB | Dimensionnement initial explicite. |
| Rétention | ex. 30 ou 90 jours | Décision métier et légale pour les backups. |
| Réseau et AMI | VPC, subnet public, AMI approuvée | Toujours explicites : aucune sélection « latest ». |

Le domaine cible les services suivants :

```text
galas-am-aix.rezal.fr          → Lespass
fedow.galas-am-aix.rezal.fr    → Fedow
cashless.galas-am-aix.rezal.fr → Laboutik
```

### 2. Planifier puis créer la fondation

1. Vérifier l'identité AWS, le compte Gala et la région.
2. Créer une fois le bucket de state Paris avec
   `infra/terraform-bootstrap/`.
3. Configurer un `backend.hcl` privé pour l'état Terraform du gala.
4. Générer et revoir le plan Terraform avec les paramètres non secrets.
5. Appliquer le plan approuvé.

La fondation crée notamment :

- EC2 Paris, EIP, Security Group HTTP/HTTPS et rôle SSM ;
- buckets de state, backups/releases et artefacts ;
- secret runtime vide ;
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

### 4. Renseigner le secret runtime

Terraform crée le conteneur du secret ; un administrateur y place ensuite une
valeur JSON contenant exactement les trois dotenv réels :

```json
{
  "fedow_env": "KEY=value\\n",
  "laboutik_env": "KEY=value\\n",
  "lespass_env": "KEY=value\\n"
}
```

L'EC2 lit uniquement son propre secret et matérialise les trois fichiers avec
le mode `0600`. Les valeurs ne doivent jamais être copiées dans un ticket, un
log, une variable CodeBuild ou le dépôt.

### 5. Valider la chaîne Test

La pipeline Test reçoit un commit de `main`, exécute les contrôles de code,
construit Lespass et pousse une image ECR taguée par le SHA Git :

```text
sha-<commit Git> → digest sha256:…
```

Elle s'arrête là : une image candidate n'est pas un déploiement. Vérifier que
les étapes Source et Build ont réussi et que le digest ECR existe.

### 6. Produire une release immuable

Une release production est un manifeste revu qui fixe les digests exacts de :

- Lespass depuis l'ECR Gala ;
- Fedow ;
- Laboutik ;
- Traefik.

Le manifeste est stocké sous `releases/<slug>/` dans le bucket de backups et
porte un `release_id` unique. Il n'utilise jamais de tag mutable.

### 7. Créer et utiliser la chaîne Production

Une fois l'ID de la nouvelle EC2 connu, la pipeline Production peut être
provisionnée. Elle comporte obligatoirement une approbation humaine :

```text
Manifeste revu → approbation → upload du manifeste → commande SSM ciblée
```

La commande SSM ne vise que l'instance allowlistée. Elle vérifie le manifeste,
le secret, l'espace disque et les conditions de backup avant le démarrage des
stacks. Une première mise en ligne exige une décision explicite : elle ne doit
pas contourner le garde-fou de backup initial sans être documentée.

### 8. Ouvrir publiquement le gala

Après un déploiement réussi et des healthchecks valides :

1. créer les enregistrements DNS OVH vers l'EIP Paris ;
2. vérifier l'émission du certificat TLS ;
3. tester Lespass, Fedow et Laboutik depuis l'extérieur ;
4. mettre le registre privé du gala à l'état `live`.

Une sauvegarde puis une restauration isolée validée sont requises avant de
supprimer une ancienne cible.

## B. Flux de développement normal

### Développer et intégrer

1. Créer une branche dédiée à la modification.
2. Lancer les tests pertinents localement.
3. Ouvrir une PR, faire relire puis fusionner dans `main`.
4. La pipeline Test construit une nouvelle candidate ECR liée au commit de
   fusion.

Les changements applicatifs ne modifient pas l'infrastructure. Les changements
dans `deploy/`, Terraform, IAM, secret, DNS ou la politique d'allowlist suivent
un plan revu séparé.

### Promouvoir une version

1. Choisir les digests produits et les dépendances exactes.
2. Composer puis revoir le manifeste de release.
3. Déclencher la pipeline Production manuellement.
4. Vérifier l'approbation humaine, le preflight et les healthchecks.
5. Enregistrer le `release_id` effectivement déployé dans le registre privé.

Un rollback consiste à promouvoir un manifeste immuable précédent ; il ne
consiste pas à réutiliser `latest` ou à reconstruire sur l'EC2.

## État actuel de l'outillage

La fondation et le bootstrap initial sont automatisés. La pipeline Test produit
déjà une image Lespass immuable. La prochaine amélioration structurante est
d'extraire le bootstrap dans un installateur d'upgrade unique, lancé au premier
boot et rejouable par SSM avec une version/commit enregistré sur l'instance.
Cela rendra les mises à jour de socle reproductibles sans maintenir une AMI
personnalisée.

## Références

- [Fondation AWS](../../infra/README.md)
- [Accès AWS](../aws-access.md)
- [Périmètre et portes de changement](../platform/scope-and-change-gates.md)
- [Registre d'un gala](gala-registry.md)
- [Démarrage, arrêt et dormance](start-stop-dormance.md)
- [Sauvegarde et restauration](backup-restore.md)
