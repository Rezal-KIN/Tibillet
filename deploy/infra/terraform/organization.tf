# This account is deliberately independent from Methodo. It may become the
# management account of an Organization that contains Gala resources only.
resource "aws_organizations_organization" "gala" {
  count = var.enable_additive_resources && var.enable_organization_bootstrap ? 1 : 0

  feature_set = "ALL"

  aws_service_access_principals = [
    "sso.amazonaws.com",
  ]

  lifecycle {
    prevent_destroy = true
  }
}
