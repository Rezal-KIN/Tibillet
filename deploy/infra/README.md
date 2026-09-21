# Infrastructure — plateforme AWS Gala

Un compte AWS indépendant (jamais Méthodo — voir mémoire `gala-aws-independent`), une EC2
par gala, isolation totale des données entre galas. Détail complet du raisonnement dans le
plan d'implémentation ; ce fichier n'est qu'un point d'entrée.

## Où regarder

- **Accès** (SSO, élévation, portabilité multi-ordinateur) : `docs/aws-access.md`.
- **Registre par gala** (statut, release déployée, rétention) : `docs/operations/gala-registry.md`.
- **Terraform** (`infra/terraform/`) : source de vérité de l'infra AWS.
  - `organization.tf`, `identity-center.tf` : Organization et IAM Identity Center Gala.
  - `gala-instances.tf`, `modules/gala/` : une EC2/secret/préfixe S3 par gala, `for_each var.galas`.
  - `delivery.tf` : pipelines CodeBuild/CodePipeline Test et Production, ECR.
  - `storage.tf` : bucket de backups chiffré (SSE-S3), bucket d'artefacts à rétention courte.
  - `secrets.tf`, `budget.tf` : Secrets Manager (valeurs jamais dans Terraform), budget AWS.
  - `versions.tf` : state local pendant l'inventaire Bapts en lecture seule. Le backend S3
    (locking natif, pas de DynamoDB) ne sera activé qu'après approbation d'une fondation
    additive ; il nécessitera alors un `backend.hcl` privé, voir `examples/backend.hcl.example`.
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

- **Production** : `<service>.<domaine-du-gala>`, ex. `fedow.galas-am-aix.rezal.fr`
  (Fedow), `cashless.galas-am-aix.rezal.fr` (Laboutik). Lespass est SANS sous-domaine sur
  son propre domaine apex (ex. `galas-am-aix.rezal.fr`), ses tenants vivant en
  sous-domaines de celui-ci (`festival.galas-am-aix.rezal.fr`).
- **Test / preview** (pipeline `tibillet-gala-test`, `delivery.tf`) : insérer `dev.` entre
  le service et le domaine du gala, ex. `fedow.dev.galas-am-aix.rezal.fr`,
  `cashless.dev.galas-am-aix.rezal.fr`. L'apex Lespass du preview devient donc
  `dev.galas-am-aix.rezal.fr` lui-même (toujours sans sous-domaine supplémentaire devant).
  Ce n'est pas encore câblé dans `delivery.tf` (la pipeline Test ne fait aujourd'hui que
  build + publish ECR, pas encore de déploiement SSM automatique vers une EC2 de preview —
  voir la section Test du plan). La convention est fixée maintenant pour que le `DOMAIN`/
  `FEDOW_DOMAIN` mis dans la config privée d'un gala de preview la respecte dès le départ.

## Ordre d'exécution (résumé)

1. `docs/aws-access.md` : un administrateur nommé active IAM Identity Center dans le
   compte Gala (décision console ponctuelle), puis exécute `install-sso-profile.sh` avec
   les vraies valeurs.
2. Pendant l'inventaire Bapts : `terraform init` et `terraform plan` utilisent un state
   local et ne font qu'observer `TibilletBapts` (`i-0cd4e52913c8ae928`). Aucun import, apply,
   instance profile, secret, bucket, pipeline ou changement de VM n'est permis.
3. Après approbation explicite d'un plan de fondation additive :
   `infra/terraform-bootstrap/` crée une seule fois le bucket de state distant. Copier
   `terraform output state_bucket_name` dans un `infra/terraform/backend.hcl` privé
   (voir `examples/backend.hcl.example`), puis activer le backend S3 dans un changement revu.
4. L'Organization et IAM Identity Center existent déjà : ils sont observés ou importés dans
   une phase dédiée, jamais recréés avec `enable_organization_bootstrap` ou
   `enable_identity_center_resources`.
5. `enable_delivery_platform = true` seulement après approbation de la connexion CodeStar
   GitHub vers `Rezal-KIN/Tibillet` et d'un plan de ressources additives. La pipeline Test
   reste build/publish sans cible Bapts ; la Production reste désactivée.

Aucune de ces étapes n'est automatique : chaque `terraform apply` reste un plan revu et
approuvé par un humain, jamais déclenché par un push applicatif.
