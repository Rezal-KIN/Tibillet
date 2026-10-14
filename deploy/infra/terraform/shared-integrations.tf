# Two shared environment secrets. Historical payment names stay stable.
# Gala-specific application keys remain in each Gala generated secret.
resource "aws_secretsmanager_secret" "stripe_test" {
  count                   = local.gala_resources_enabled ? 1 : 0
  depends_on              = [aws_iam_role_policy.foundation_build]
  name                    = "${var.project_name}/shared/integrations-stripe-test"
  description             = "Shared dev configuration: Stripe, CAWL, mail, site settings and admin. Gala-specific keys stay separate."
  recovery_window_in_days = 7
  tags                    = local.common_tags
  lifecycle { prevent_destroy = true }
}

resource "aws_secretsmanager_secret" "stripe_live" {
  count                   = local.gala_resources_enabled ? 1 : 0
  depends_on              = [aws_iam_role_policy.foundation_build]
  name                    = "${var.project_name}/shared/integrations-stripe-live"
  description             = "Shared production configuration: Stripe, CAWL, mail, site settings and admin. Gala-specific keys stay separate."
  recovery_window_in_days = 7
  tags                    = local.common_tags
  lifecycle { prevent_destroy = true }
}

output "shared_stripe_test_secret_arn" {
  value = local.gala_resources_enabled ? aws_secretsmanager_secret.stripe_test[0].arn : null
}

output "shared_stripe_live_secret_arn" {
  value = local.gala_resources_enabled ? aws_secretsmanager_secret.stripe_live[0].arn : null
}

output "environment_secret_arns" {
  value = local.gala_resources_enabled ? {
    dev  = aws_secretsmanager_secret.stripe_test[0].arn
    prod = aws_secretsmanager_secret.stripe_live[0].arn
  } : {}
}
