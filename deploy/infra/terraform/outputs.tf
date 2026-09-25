output "aws_account_id" {
  value       = data.aws_caller_identity.current.account_id
  description = "The independent Gala AWS account targeted by this Terraform configuration."
}

output "backup_bucket_name" {
  value       = var.enable_additive_resources && var.enable_backup_storage ? aws_s3_bucket.backups[0].bucket : null
  description = "Encrypted, private backup bucket."
}

output "artifact_bucket_name" {
  value       = local.delivery_resources_enabled ? aws_s3_bucket.artifacts[0].bucket : null
  description = "Short-retention CodePipeline artifact bucket when delivery is enabled."
}

output "galas" {
  value = {
    for slug, gala in module.gala : slug => {
      instance_id          = gala.instance_id
      generated_secret_arn = gala.generated_secret_arn
      backup_prefix        = gala.backup_prefix
    }
  }
  description = "Derived per-gala fields (instance, secret ARN, backup prefix). Public traffic uses one shared EIP."
}

output "shared_public_ip" {
  value       = local.gala_resources_enabled ? aws_eip.shared_public[0].public_ip : null
  description = "The one stable public IPv4 address used by the active Gala."
}

output "shared_eip_allocation_id" {
  value       = local.gala_resources_enabled ? aws_eip.shared_public[0].id : null
  description = "Allocation ID used by the explicit active-Gala switch workflow."
}

output "active_public_security_group_id" {
  value       = local.gala_resources_enabled ? aws_security_group.active_public[0].id : null
  description = "Public ingress security group attached only to the active Gala."
}

output "active_gala_parameter_name" {
  value       = local.gala_resources_enabled ? aws_ssm_parameter.active_gala[0].name : null
  description = "SSM Parameter Store key recording the Gala currently holding the shared EIP."
}
