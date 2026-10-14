output "generated_secret_arn" {
  value       = var.shared_stripe_secret_arn
  description = "Environment secret containing this Gala's stable generated-key entry."
}

output "instance_id" {
  value       = var.create_instance ? (var.protect_from_destruction ? aws_instance.runtime[0].id : aws_instance.retirable[0].id) : null
  description = "Newly created instance ID. Existing instances are imported separately before management."
}

output "primary_eni_id" {
  value       = var.create_instance ? (var.protect_from_destruction ? aws_instance.runtime[0].primary_network_interface_id : aws_instance.retirable[0].primary_network_interface_id) : null
  description = "Primary network interface eligible for the reviewed shared-EIP switch."
}

output "runtime_security_group_id" {
  value       = aws_security_group.runtime.id
  description = "Gala-owned security group required when the reviewed switch changes ENI groups."
}

output "backup_prefix" {
  value = local.backup_prefix
}
