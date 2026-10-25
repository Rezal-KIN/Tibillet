variable "aws_region" {
  description = "AWS region hosting the Terraform state bucket. Should match infra/terraform's aws_region."
  type        = string
  default     = "eu-west-3"
}

variable "project_name" {
  description = "Stable project identifier used in the Paris state bucket name. Must match infra/terraform's project_name."
  type        = string
  default     = "tibillet-gala-paris"
}

variable "environment" {
  description = "Matches infra/terraform's environment (test or production state, kept in separate keys within the same bucket)."
  type        = string
  default     = "production"
}
