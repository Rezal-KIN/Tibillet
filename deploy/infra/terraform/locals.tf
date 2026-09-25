locals {
  name_prefix                  = "${var.project_name}-${var.environment}"
  gala_resources_enabled       = var.enable_additive_resources && var.enable_backup_storage
  delivery_resources_enabled   = local.gala_resources_enabled && var.enable_delivery_platform
  production_resources_enabled = local.delivery_resources_enabled && var.enable_production_pipeline
  production_target_galas = local.production_resources_enabled ? {
    for slug, gala in var.galas : slug => gala
    if gala.create_instance
  } : {}
  production_iam_role_prefix = {
    for slug, gala in local.production_target_galas :
    slug => length("${local.name_prefix}-production-${slug}-pipeline") <= 64 ?
    "${local.name_prefix}-production-${slug}" :
    "${var.project_name}-p-${substr(slug, 0, 20)}-${substr(sha1(slug), 0, 8)}"
  }
  foundation_codebuild_role_arn = var.foundation_codebuild_role_arn != "" ? var.foundation_codebuild_role_arn : try(aws_iam_role.foundation_build[0].arn, "")
  foundation_pipeline_enabled   = local.delivery_resources_enabled && var.enable_foundation_pipeline

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
    Repository  = "Rezal-KIN/Tibillet"
    DataClass   = "gala-isolated"
  }

  backup_bucket_name = var.backup_bucket_name != "" ? var.backup_bucket_name : "${local.name_prefix}-${data.aws_caller_identity.current.account_id}-backups"
}
