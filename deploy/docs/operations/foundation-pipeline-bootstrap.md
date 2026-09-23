# Bootstrap de la pipeline Infrastructure

La pipeline **Foundation** est le point d'entrée manuel pour ajouter un gala.
Elle crée l'EC2, son EIP, son secret vide, ses préfixes S3, puis la pipeline
Production verrouillée sur cette EC2. Elle ne reçoit jamais de secret runtime.

## Pré-requis uniques

Une pipeline ne peut pas se créer elle-même. Un administrateur réalise donc une
fois un `terraform plan`, le révise, puis applique la configuration qui active :

```hcl
enable_foundation_pipeline   = true
foundation_codebuild_role_arn = "arn:aws:iam::318629836660:role/..."
terraform_state_bucket_name  = "..."
```

Le rôle indiqué est un rôle CodeBuild élevé, approuvé séparément. Il doit être
limité au compte Gala et pouvoir : lire/verrouiller l'état Terraform, lire et
écrire `foundation-inputs/galas.json` dans le bucket de sauvegardes, écrire les
artefacts/logs, utiliser la connexion GitHub approuvée et effectuer les actions
Terraform explicitement autorisées. Il ne reçoit pas `GetSecretValue` sur les
secrets runtime.

Avant la première exécution, le catalogue doit être créé dans le bucket de
sauvegardes à la clé `foundation-inputs/galas.json`. Il contient la
configuration **non secrète** complète des galas déjà gérés : réseau commun,
AMI et bloc `galas`. Cette étape de seed protège contre un plan qui oublierait
un gala déjà présent dans le state. Le fichier est versionné par le bucket ; il
ne contient ni dotenv, ni token, ni ARN de secret.

## Exécution d'un nouveau gala

Dans CodePipeline, ouvrir `...-foundation`, choisir **Release change** et
saisir :

- `GalaSlug`, `GalaDomain` ;
- `VpcId`, `SubnetId`, `Ec2AmiId` ;
- `InstanceType`, taille du volume et, si nécessaire, CIDR SSH d'urgence.

La pipeline valide ces valeurs, fusionne le gala dans le catalogue, calcule le
plan Terraform et s'arrête à l'approbation. L'approbateur lit
`foundation-plan.txt` et le tfvars produit. L'étape suivante applique le plan
binaire exactement produit, puis seulement enregistre le nouveau catalogue.

Un slug déjà existant, un réseau différent du catalogue, une AMI non conforme
ou `0.0.0.0/0` pour SSH font échouer le plan. Pour modifier un gala existant,
ouvrir une PR Terraform revue : la pipeline Foundation est volontairement une
pipeline d'ajout, pas un éditeur générique de production.
