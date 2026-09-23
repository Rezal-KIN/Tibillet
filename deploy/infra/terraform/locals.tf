locals {
  name_prefix                  = "${var.project_name}-${var.environment}"
  delivery_resources_enabled   = var.enable_additive_resources && var.enable_backup_storage && var.enable_delivery_platform
  production_resources_enabled = local.delivery_resources_enabled && var.enable_production_pipeline
  production_target_galas = local.production_resources_enabled ? {
    for slug, gala in var.galas : slug => gala
    if gala.create_instance
  } : {}
  foundation_pipeline_enabled = local.delivery_resources_enabled && var.enable_foundation_pipeline

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
    Repository  = "Rezal-KIN/Tibillet"
    DataClass   = "gala-isolated"
  }

  backup_bucket_name = var.backup_bucket_name != "" ? var.backup_bucket_name : "${local.name_prefix}-${data.aws_caller_identity.current.account_id}-backups"
}
