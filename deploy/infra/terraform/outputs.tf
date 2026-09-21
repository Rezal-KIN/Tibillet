output "aws_account_id" {
  value       = data.aws_caller_identity.current.account_id
  description = "The independent Gala AWS account targeted by this Terraform configuration."
}

output "bapts_observed_runtime" {
  value = {
    instance_id = data.aws_instance.bapts.id
    name        = data.aws_instance.bapts.tags["Name"]
    state       = data.aws_instance.bapts.instance_state
    region      = var.aws_region
  }
  description = "Read-only observation of the sole allowlisted live runtime during the plan-only phase."
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
      instance_id        = gala.instance_id
      public_ip          = gala.public_ip
      runtime_secret_arn = gala.runtime_secret_arn
      backup_prefix      = gala.backup_prefix
    }
  }
  description = "Derived per-gala fields (instance, IP, secret ARN, backup prefix). The registry (registry/galas.json, see docs/operations/gala-registry.md) holds only what Terraform cannot derive: platform, release, retention, status."
}
