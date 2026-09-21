variable "aws_region" {
  description = "AWS region hosting the Gala runtime."
  type        = string
  default     = "eu-north-1"

  validation {
    condition     = var.aws_region == "eu-north-1"
    error_message = "The current plan-only scope permits only the Bapts runtime region eu-north-1."
  }
}

variable "gala_account_id" {
  description = "The sole AWS account permitted for this Gala Terraform configuration."
  type        = string
  default     = "318629836660"

  validation {
    condition     = var.gala_account_id == "318629836660"
    error_message = "The Gala account allowlist is fixed to 318629836660."
  }
}

variable "enable_additive_resources" {
  description = "Allows creation of approved additive AWS resources only after a separately reviewed plan. Keep false during Bapts inventory and plan-only work."
  type        = bool
  default     = false
}

variable "enable_backup_storage" {
  description = "Creates the encrypted, versioned backups bucket used for future gala DB backups and promoted release manifests. Deferred to the dedicated backups project (plan Phase 5) — keep false until that work is separately approved, even while delivery/ECR resources are enabled."
  type        = bool
  default     = false
}

variable "enable_secrets_scaffolding" {
  description = "Creates the empty Secrets Manager runtime template container. The secrets mechanism decision (Infisical vs Secrets Manager) is a separate Phase 5 approval — keep false until that decision is made, even while delivery/ECR resources are enabled."
  type        = bool
  default     = false
}

variable "bapts_instance_id" {
  description = "The only live runtime instance permitted for read-only observation in this phase."
  type        = string
  default     = "i-0cd4e52913c8ae928"

  validation {
    condition     = var.bapts_instance_id == "i-0cd4e52913c8ae928"
    error_message = "The Bapts instance allowlist is fixed to i-0cd4e52913c8ae928."
  }
}

variable "bapts_instance_name" {
  description = "Expected Name tag for the only in-scope live runtime."
  type        = string
  default     = "TibilletBapts"

  validation {
    condition     = var.bapts_instance_name == "TibilletBapts"
    error_message = "The Bapts Name-tag allowlist is fixed to TibilletBapts."
  }
}

variable "project_name" {
  description = "Stable project identifier used in resource names and tags."
  type        = string
  default     = "tibillet-gala"
}

variable "environment" {
  description = "Infrastructure environment: test or production."
  type        = string
  default     = "test"

  validation {
    condition     = contains(["test", "production"], var.environment)
    error_message = "environment must be test or production."
  }
}

variable "enable_organization_bootstrap" {
  description = "Creates an AWS Organization from the current Gala account. Set only once after a human has confirmed this account is the intended management account."
  type        = bool
  default     = false
}

variable "identity_center_region" {
  description = "Home region of the existing Gala IAM Identity Center."
  type        = string
  default     = "eu-west-3"

  validation {
    condition     = var.identity_center_region == "eu-west-3"
    error_message = "The existing Gala IAM Identity Center home region is eu-west-3."
  }
}

variable "enable_identity_center_resources" {
  description = "Creates Gala-only Identity Center groups, permission sets, and account assignments after Identity Center has been enabled by a human in the Gala account."
  type        = bool
  default     = false
}

variable "administrator_users" {
  description = "The two initial named Gala administrators. Terraform never stores passwords or MFA devices."
  type = map(object({
    email       = string
    given_name  = string
    family_name = string
  }))
  default = {}
}

variable "enable_production_pipeline" {
  description = "Creates the manually triggered Production pipeline after an exact target instance and SSM document are known."
  type        = bool
  default     = false
}

variable "production_target_instance_id" {
  description = "Explicit Gala EC2 instance ID targeted by the manually triggered Production pipeline. Empty keeps production delivery disabled."
  type        = string
  default     = ""
}

variable "production_gala_slug" {
  description = "Slug of the one Gala EC2 targeted by the initial Production pipeline. It scopes the SSM document config path and the S3 release-manifest prefix."
  type        = string
  default     = ""

  validation {
    condition     = var.production_gala_slug == "" || can(regex("^[a-z0-9][a-z0-9-]{1,62}$", var.production_gala_slug))
    error_message = "production_gala_slug must be empty or a lowercase Gala slug."
  }
}

variable "production_release_manifest_path" {
  description = "Repo-relative immutable release manifest selected by the manually run Production pipeline."
  type        = string
  default     = "releases/production.json"
}

variable "enable_delivery_platform" {
  description = "Creates shared ECR, CodeBuild, CodePipeline, and short-lived artifact storage. Keep false until AWS account inventory and CodeStar connection approval are complete."
  type        = bool
  default     = false
}

variable "application_github_owner" {
  description = "GitHub organization owning the Rezal fork of the TiBillet application."
  type        = string
  default     = ""
}

variable "application_github_repository" {
  description = "Fork repository built by CodeBuild, for example Lespass-gala. Empty keeps delivery disabled."
  type        = string
  default     = ""
}

variable "github_owner" {
  description = "GitHub organization that owns this combined application and Gala deployment repository."
  type        = string
  default     = "Rezal-KIN"
}

variable "github_repository" {
  description = "Combined application and Gala deployment repository name."
  type        = string
  default     = "Tibillet"
}

variable "production_source_branch" {
  description = "Branch or tag containing reviewed immutable production release manifests."
  type        = string
  default     = "production"
}

variable "test_source_branch" {
  description = "Branch automatically built by the Test pipeline."
  type        = string
  default     = "main"
}

variable "codebuild_log_retention_days" {
  description = "Short retention for CodeBuild diagnostics."
  type        = number
  default     = 7

  validation {
    condition     = contains([1, 3, 5, 7, 14], var.codebuild_log_retention_days)
    error_message = "Use a short, explicit CodeBuild log retention period."
  }
}

variable "ecr_release_retention_count" {
  description = "Number of immutable Lespass releases retained in ECR."
  type        = number
  default     = 5

  validation {
    condition     = var.ecr_release_retention_count >= 3 && var.ecr_release_retention_count <= 10
    error_message = "Keep between 3 and 10 ECR releases."
  }
}

variable "backup_bucket_name" {
  description = "Globally unique S3 bucket for encrypted Gala backups. Empty means Terraform derives a name from this AWS account."
  type        = string
  default     = ""
}

variable "backup_retention_days" {
  description = "Initial hot-backup retention. Confirm the legal retention policy before changing it."
  type        = number
  default     = 30
}

variable "budget_limit_usd" {
  description = "Monthly Gala account budget threshold. Notifications are configured after an email recipient is provided."
  type        = number
  default     = 0
}

variable "budget_notification_email" {
  description = "Email used only for AWS budget notifications. Empty disables the budget resource."
  type        = string
  default     = ""
}

variable "extra_tags" {
  description = "Additional non-sensitive tags."
  type        = map(string)
  default     = {}
}

variable "vpc_id" {
  description = "Existing Gala VPC ID. Required only when galas are declared."
  type        = string
  default     = ""
}

variable "subnet_id" {
  description = "Existing public Gala subnet ID. Required only when galas are declared."
  type        = string
  default     = ""
}

variable "ec2_ami_id" {
  description = "Explicit approved Ubuntu or Amazon Linux AMI ID for new Gala EC2 instances. Never use a moving latest-AMI lookup for a live gala."
  type        = string
  default     = ""
}

variable "galas" {
  description = "Independent Gala instances. A new gala has its own EC2, secret, S3 prefix, DB volumes, and platform generation."
  type = map(object({
    platform                 = string
    domain                   = string
    instance_type            = optional(string, "t3.medium")
    root_volume_size_gib     = optional(number, 40)
    ssh_emergency_cidrs      = optional(list(string), [])
    create_instance          = optional(bool, false)
    protect_from_destruction = optional(bool, true)
  }))
  default = {}

  validation {
    condition = alltrue([
      for gala in values(var.galas) : contains(["v1", "v2-preview", "v2"], gala.platform)
    ])
    error_message = "A Gala platform must be v1, v2-preview, or v2."
  }
}
