output "generated_secret_arn" {
  value       = aws_secretsmanager_secret.generated.arn
  description = "Generated application keys and database credentials for the target Gala."
}

output "instance_id" {
  value       = var.create_instance ? aws_instance.runtime[0].id : null
  description = "Newly created instance ID. Existing instances are imported separately before management."
}

output "primary_eni_id" {
  value       = var.create_instance ? aws_instance.runtime[0].primary_network_interface_id : null
  description = "Primary network interface eligible for the reviewed shared-EIP switch."
}

output "backup_prefix" {
  value = local.backup_prefix
}
