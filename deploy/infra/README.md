# Infrastructure — plateforme AWS Gala

Un compte AWS indépendant (jamais Méthodo — voir mémoire `gala-aws-independent`), une EC2
par gala, isolation totale des données entre galas. Détail complet du raisonnement dans le
plan d'implémentation ; ce fichier n'est qu'un point d'entrée.

## Où regarder

- **Architecture cible et écarts réels** : `../docs/ARCHITECTURE-GALAS.md`.
- **Accès** (SSO, élévation, portabilité multi-ordinateur) : `docs/aws-access.md`.
- **Registre par gala** (statut, release déployée, rétention) : `docs/operations/gala-registry.md`.
- **Guide de déploiement et de développement** :
  `docs/operations/new-gala-deployment-and-development-workflow.md`.
- **Terraform** (`infra/terraform/`) : source de vérité de l'infra AWS.
  - `organization.tf`, `identity-center.tf` : Organization et IAM Identity Center Gala.
  - `gala-instances.tf`, `modules/gala/` : une EC2, des clés propres et un préfixe S3 par gala, `for_each var.galas`.
  - `active-gala.tf`, `active-gala-delivery.tf` : une IP élastique commune et une pipeline manuelle de bascule du gala actif.
  - `shared-integrations.tf` : secrets Secrets Manager communs Stripe test,
    Stripe live et SMTP, sans valeur dans Terraform.
  - `delivery.tf` : pipeline CodeBuild/CodePipeline Test et ECR ; la promotion immutable est
    définie dans `production-delivery.tf`.
  - `storage.tf` : bucket de backups chiffré (SSE-S3), qui conserve aussi les manifestes de
    release promus, et bucket d'artefacts à rétention courte.
  - `modules/gala/bootstrap-runtime.sh.tftpl` : bootstrap idempotent de l'EC2 Paris.
  - `budget.tf` : budget AWS. Les valeurs Secrets Manager ne sont jamais dans Terraform.
  - `versions.tf` : backend S3 (locking natif, pas de DynamoDB), activé avec un
    `backend.hcl` privé après approbation de la fondation, voir `examples/backend.hcl.example`.
  - `examples/gala.auto.tfvars.example`, `examples/backend.hcl.example` : à copier en
    fichiers privés (`.tfvars`, `backend.hcl`), jamais commités.
- **State distant** (`infra/terraform-bootstrap/`) : config séparée, state local, appliquée
  une seule fois. Crée uniquement le bucket S3 qui héberge le state de `infra/terraform`
  (impossible d'y faire référence depuis un backend qu'il doit lui-même configurer).
- **Releases immuables** (`releases/`) : manifestes `release_id` → digests figés. Schéma dans
  `releases/examples/gala-v1-release.json`.
- **Scripts runtime sur l'EC2** (`tools/runtime/`) : `preflight`, `backup-postgres`,
  `restore-postgres`, `deploy-release`, `healthcheck`, `start-stacks`, `stop-stacks`.
- **Profil SSO portable** (`tools/aws/install-sso-profile.sh`) : installe les profils
  `gala-operator`/`gala-elevated`/`gala-administrator` dans `~/.aws/config` sur un nouvel
  ordinateur.
- **Timers systemd** (`systemd/`) : backup planifié, démarrage des stacks au boot.
- **Buildspecs** (`buildspec/`) : ce que CodeBuild exécute pour les pipelines Test et
  Production.

## Conventions de nommage — domaines

- **Production** : les mêmes noms pour tous les galas, ex. `fedow.galas-am-aix.rezal.fr`
  (Fedow), `cashless.galas-am-aix.rezal.fr` (Laboutik). Lespass est SANS sous-domaine sur
  le domaine apex commun (`galas-am-aix.rezal.fr`), ses tenants vivant en
  sous-domaines de celui-ci (`festival.galas-am-aix.rezal.fr`).
- **Smoke** : les mêmes noms publics que Production. Un seul environnement
  reçoit l'IP fixe à la fois ; la pipeline manuelle Gala actif fait la bascule.
  Les images Fedow, Laboutik et Traefik de Smoke sont épinglées dans
  `deploy/test-images.json`. Lespass suit le commit `main` construit en Test.

## Ordre d'exécution (résumé)

1. `docs/aws-access.md` : un administrateur nommé active IAM Identity Center dans le
   compte Gala (décision console ponctuelle), puis exécute `install-sso-profile.sh` avec
   les vraies valeurs.
2. La fondation runtime est exclusivement à Paris (`eu-west-3`). `TibilletBapts` est arrêtée
   et reste une archive de secours Stockholm, hors graphe Terraform et hors cible de déploiement.
3. Après approbation explicite d'un plan de fondation additive :
   `infra/terraform-bootstrap/` crée une seule fois le bucket de state distant. Copier
   `terraform output state_bucket_name` dans un `infra/terraform/backend.hcl` privé
   (voir `examples/backend.hcl.example), puis activer le backend S3 dans un changement revu.
4. Une pipeline CodePipeline **Foundation**, déclenchée manuellement, reçoit
   seulement le nom du nouveau gala. Le reste provient de la configuration
   permanente. Elle produit un plan archivé, refuse automatiquement les
   changements hors création du gala demandé, puis l'applique sans approbation
   manuelle du plan ;
   les clés propres aux galas sont générées une fois après l'apply, les identifiants
   Stripe test/live et SMTP communs sont renseignés séparément. Son premier bootstrap et le seed du catalogue privé
   des galas sont des actions Terraform administrateur ponctuelles.
5. `enable_delivery_platform = true` seulement après approbation de la connexion CodeStar
   GitHub vers `Rezal-KIN/Tibillet`, création du bucket de sauvegardes/releases et plan de
   ressources additives. La pipeline Test build/publish une candidate puis
   déploie l'unique EC2 Smoke ; Terraform
   crée ensuite une pipeline Production manuelle par gala, verrouillée sur sa seule EC2 Paris.
   La pipeline distincte `...-active-gala` attribue l'unique IP publique après
   vérifications locales et approbation ; créer un gala ne le rend pas public.
6. Après le bootstrap, une sauvegarde et une restauration isolée validée précèdent toute
   première migration DNS depuis Stockholm ou promotion publique. Les bascules
   ultérieures déplacent l'IP élastique sans modification DNS.

La création d'un nouveau gala est automatique **dans Foundation** après
contrôle du plan. Le bootstrap initial ou une migration d'infrastructure
existante suit un plan séparé et revu. Une release Production garde son
approbation humaine après la validation des images testées.
