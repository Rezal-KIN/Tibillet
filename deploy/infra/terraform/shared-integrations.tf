# External credentials are shared by all Galas, but Test can never read live
# Stripe keys. Terraform creates containers and IAM only, not secret values.
resource "aws_secretsmanager_secret" "stripe_test" {
  count                   = local.gala_resources_enabled ? 1 : 0
  depends_on              = [aws_iam_role_policy.foundation_build]
  name                    = "${var.project_name}/shared/integrations-stripe-test"
  description             = "Test Stripe credentials of the shared Gala Stripe account."
  recovery_window_in_days = 7
  tags                    = local.common_tags
  lifecycle { prevent_destroy = true }
}

resource "aws_secretsmanager_secret" "stripe_live" {
  count                   = local.gala_resources_enabled ? 1 : 0
  depends_on              = [aws_iam_role_policy.foundation_build]
  name                    = "${var.project_name}/shared/integrations-stripe-live"
  description             = "Live Stripe credentials of the shared Gala Stripe account."
  recovery_window_in_days = 7
  tags                    = local.common_tags
  lifecycle { prevent_destroy = true }
}

resource "aws_secretsmanager_secret" "shared_mail" {
  count                   = local.gala_resources_enabled ? 1 : 0
  depends_on              = [aws_iam_role_policy.foundation_build]
  name                    = "${var.project_name}/shared/integrations-mail"
  description             = "Shared Gala SMTP account and common site settings."
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

output "shared_mail_secret_arn" {
  value = local.gala_resources_enabled ? aws_secretsmanager_secret.shared_mail[0].arn : null
}
