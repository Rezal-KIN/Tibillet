# Bootstrap de la pipeline Infrastructure

**Le code décrit ici est la cible versionnée ; vérifier son installation AWS
avant de lancer un gala.** Foundation reçoit le nom du gala et n'a pas
d'approbation manuelle du plan pour une création normale.
Voir le [protocole de déploiement](new-gala-deployment-and-development-workflow.md)
avant toute nouvelle exécution.

La pipeline **Foundation** est le point d'entrée manuel pour ajouter un gala.
Elle crée l'EC2, son conteneur de clés, ses préfixes S3, puis la pipeline
Production verrouillée sur cette EC2. Après l'apply, une étape Finalize génère
les clés une seule fois, vérifie cloud-init et le runtime sur l'EC2 exacte via
SSM, puis enregistre le catalogue. Elle ne reçoit jamais de
secret Stripe ou SMTP.

## Pré-requis uniques

Une pipeline ne peut pas se créer elle-même. Un administrateur réalise donc une
fois un `terraform plan`, le révise, puis applique la configuration qui active :

```hcl
enable_foundation_pipeline   = true
manage_foundation_codebuild_role = true
terraform_state_bucket_name  = "..."
```

Terraform crée alors un rôle CodeBuild dédié, limité au compte Gala, aux
ressources `tibillet-gala-paris` et à Paris. Un ARN de rôle approuvé peut aussi
être fourni à la place. Dans les deux cas, il doit pouvoir lire/verrouiller
l'état Terraform, lire et écrire `foundation-inputs/galas.json`, écrire les
artefacts/logs, utiliser la connexion GitHub approuvée et effectuer les actions
Terraform nécessaires. Il peut initialiser les seuls secrets `*/generated` ;
il ne reçoit pas `GetSecretValue` ni accès aux identifiants Stripe/SMTP.

Avant la première exécution, le catalogue doit être créé dans le bucket de
sauvegardes à la clé `foundation-inputs/galas.json`. Il contient la
configuration **non secrète** complète des galas déjà gérés : réseau commun,
AMI et bloc `galas`. Cette étape de seed protège contre un plan qui oublierait
un gala déjà présent dans le state. Le fichier est versionné par le bucket ; il
ne contient ni dotenv, ni token, ni ARN de secret.

## Exécution d'un nouveau gala

Dans CodePipeline, ouvrir `...-foundation`, choisir **Release change** et
saisir **`GalaName` uniquement**. Le slug est déduit du nom ; le réseau,
l'AMI, le domaine et la capacité standard proviennent du catalogue et de la
configuration Foundation versionnée.

La pipeline valide le nom, fusionne le gala dans le catalogue, calcule le
plan Terraform et refuse toute suppression, remplacement, modification d'un
autre gala ou changement de plateforme inattendu. Elle applique ensuite le
plan binaire exactement produit. Une étape Finalize indépendante initialise les
clés stables du nouveau gala (et préserve celles des galas existants), vérifie
le bootstrap via SSM, puis seulement enregistre le nouveau catalogue.
Finalize peut être réessayée sans
rejouer un plan Terraform déjà appliqué.

Une relance avec le même nom et la même configuration est un *no-op* sûr ou
reprend l'échec partiel. Une collision avec une configuration différente est
refusée. Pour modifier un gala existant, ouvrir une PR Terraform revue :
Foundation est une pipeline d'ajout, pas un éditeur générique de production.
