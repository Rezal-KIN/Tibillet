output "runtime_secret_arn" {
  value       = aws_secretsmanager_secret.runtime.arn
  description = "Only the target Gala EC2 may read this runtime secret."
}

output "instance_id" {
  value       = var.create_instance ? aws_instance.runtime[0].id : null
  description = "Newly created instance ID. Existing instances are imported separately before management."
}

output "public_ip" {
  value       = var.create_instance ? aws_eip.runtime[0].public_ip : null
  description = "Stable public address for this Gala when Terraform created it."
}

output "backup_prefix" {
  value = local.backup_prefix
}
