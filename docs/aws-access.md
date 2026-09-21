# Accès AWS — compte Gala (portable, sans clé durable)

Ce document décrit comment un humain autorisé (ou un agent agissant pour lui) obtient un
accès temporaire au compte AWS Gala depuis n'importe quel ordinateur, sans jamais stocker
de clé d'accès permanente. Le compte AWS Gala est **indépendant** du compte Méthodo :
aucune Organization, ressource, identité ou convention d'accès n'est partagée entre les
deux. Voir la mémoire `gala-aws-independent` si ce point doit être re-vérifié.

## Modèle

- Deux humains nommés sont administrateurs (`Gala-AWS-Administrators`).
- Le travail courant (agents inclus) utilise le rôle `Gala-Operator` : lecture large,
  déclenchement CodeBuild/CodePipeline, exécution SSM limitée aux documents/instances
  gala. Ce rôle ne peut pas lire de secret, muter IAM/Organizations/Identity Center, ni
  s'auto-élever (`sts:AssumeRole*` refusé explicitement).
- `Gala-Elevated-Operators` est vide par défaut. Un humain s'y ajoute temporairement (ou
  ouvre une session `gala-elevated` déjà autorisée) pour une action sensible précise
  (`terraform apply`, mutation de secret, IAM, réseau). Session de 12 h — le maximum
  imposé par AWS pour la durée de session d'un permission set (`PT12H`, voir
  `infra/terraform/identity-center.tf`).
- Aucune clé IAM permanente n'existe pour un usage courant. `~/.aws/credentials` ne doit
  contenir aucune clé Gala.

### Deux durées de session distinctes — ne pas les confondre

AWS Identity Center a deux réglages de durée séparés :

1. **Durée de session du permission set** (`session_duration` sur
   `aws_ssoadmin_permission_set`, gérée par Terraform) : combien de temps les identifiants
   STS temporaires émis pour un rôle restent valides une fois obtenus. Operator = 6 h,
   Elevated = 12 h (max AWS), Administrator = 6 h.
2. **Durée de session du portail d'accès** (réglage global de l'instance Identity Center,
   `Settings > Authentication > Session settings`, **pas gérable par Terraform** — aucune
   ressource `aws_ssoadmin_*` ne l'expose au 2026-09, réglage console/API uniquement) :
   combien de temps avant qu'un humain doive refaire `aws sso login` + MFA dans le
   navigateur. Réglée manuellement par un administrateur à **14 jours**.

**Implication de sécurité à connaître** : la durée du portail est unique pour toute
l'instance, pas par rôle. Tant que la session portail de 14 jours est valide, `aws sso
login --profile gala-elevated` réémet de nouveaux identifiants Elevated à partir du token
portail déjà en cache **sans redemander de MFA**. La garantie « nouvelle MFA à chaque
élévation » décrite plus haut ne tient donc que pour la première élévation après expiration
du portail (ou après une déconnexion explicite) — pas pour chaque élévation individuelle
pendant les 14 jours. Si une garantie MFA-par-élévation stricte redevient nécessaire, il
faudra soit raccourcir la durée portail, soit forcer une déconnexion (`aws sso logout`)
avant toute élévation.

## Première installation sur un nouvel ordinateur

Prérequis : AWS CLI v2 et Terraform installés.

```bash
tools/aws/install-sso-profile.sh
```

Ce script écrit un bloc `[sso-session gala]` + trois profils (`gala-operator`,
`gala-elevated`, `gala-administrator`) dans `~/.aws/config`. Il ne contient que des
valeurs publiques (URL du portail SSO, région, account ID) — jamais de secret. Si les
placeholders `__GALA_...__` n'ont pas encore été remplacés dans le script par les vraies
valeurs (disponibles auprès d'un administrateur nommé), le script refuse de s'exécuter.

## Connexion quotidienne

```bash
aws sso login --profile gala-operator
aws sts get-caller-identity --profile gala-operator
export AWS_PROFILE=gala-operator
export AWS_REGION=eu-north-1
```

L'ouverture du navigateur, la connexion et la MFA sont faites par l'humain, au maximum une
fois tous les 14 jours (durée de session du portail, voir ci-dessus). Le token de session
est stocké dans `~/.aws/sso/cache/`, et n'est jamais commité. Les identifiants STS de rôle
(6 h pour Operator) sont réémis silencieusement à partir de ce token tant qu'il est valide.
Un agent travaillant pour l'humain utilise cette session déjà ouverte — il ne reçoit et ne
demande aucune clé, mot de passe ou token.

## Élévation temporaire pour une action sensible

1. Un humain identifie précisément l'action à effectuer (ex. `terraform apply`,
   rotation d'un secret, modification IAM).
2. `aws sso login --profile gala-elevated` (session Elevated de 12 h ; ne redemande une
   MFA que si la session portail de 14 jours a expiré — voir l'avertissement ci-dessus).
3. L'agent exécute **uniquement** l'opération convenue avec `AWS_PROFILE=gala-elevated`.
4. Retour immédiat à `AWS_PROFILE=gala-operator` pour tout le reste.

Ne jamais garder `gala-elevated` exporté au-delà de l'action convenue.

## Vérification que le modèle fonctionne

- `aws sso login --profile gala-operator` + `aws sts get-caller-identity` réussissent
  depuis un second ordinateur, sans aucune clé dans `~/.aws/credentials`.
- Avec `gala-operator` : `codepipeline:StartPipelineExecution` et `ssm:SendCommand` sur
  une instance gala fonctionnent ; `secretsmanager:GetSecretValue`,
  `iam:CreateUser`, `organizations:*`, `sso-admin:*` et `sts:AssumeRole*` sont refusés
  (Deny explicite, voir `infra/terraform/identity-center.tf`).
- Avec `gala-elevated` : l'action convenue passe ; la session expire après 12 h.

## Ce que ce document ne couvre pas

- Le bootstrap initial d'IAM Identity Center dans le compte Gala (décision console
  ponctuelle par un administrateur, car AWS choisit la région d'accueil SSO) — voir
  `infra/terraform/identity-center.tf` pour ce que Terraform crée *après* ce bootstrap.
- Les runbooks d'exploitation (start/stop, backup/restore, incident) — voir
  `docs/operations/`.
