# IAM Identity Center must first be enabled manually in the independent Gala
# management account. Enabling it is a one-time console decision because AWS
# chooses the Identity Center home region and presents the SSO portal there.
data "aws_ssoadmin_instances" "gala" {
  provider = aws.identity_center
  count    = var.enable_additive_resources && var.enable_identity_center_resources ? 1 : 0
}

locals {
  identity_center_resources_enabled = var.enable_additive_resources && var.enable_identity_center_resources
  identity_center_instance_arn      = local.identity_center_resources_enabled ? one(data.aws_ssoadmin_instances.gala[0].arns) : null
  identity_store_id                 = local.identity_center_resources_enabled ? one(data.aws_ssoadmin_instances.gala[0].identity_store_ids) : null
}

resource "aws_identitystore_group" "administrators" {
  provider          = aws.identity_center
  count             = local.identity_center_resources_enabled ? 1 : 0
  identity_store_id = local.identity_store_id
  display_name      = "Gala-AWS-Administrators"
  description       = "Named human administrators of the independent Gala AWS Organization."
}

resource "aws_identitystore_group" "operators" {
  provider          = aws.identity_center
  count             = local.identity_center_resources_enabled ? 1 : 0
  identity_store_id = local.identity_store_id
  display_name      = "Gala-Operators"
  description       = "Named human operators whose temporary sessions may be used for routine agent work."
}

resource "aws_identitystore_group" "elevated_operators" {
  provider          = aws.identity_center
  count             = local.identity_center_resources_enabled ? 1 : 0
  identity_store_id = local.identity_store_id
  display_name      = "Gala-Elevated-Operators"
  description       = "Empty by default. A human adds a member temporarily before a sensitive operation."
}

resource "aws_identitystore_user" "administrators" {
  provider = aws.identity_center
  for_each = local.identity_center_resources_enabled ? var.administrator_users : {}

  identity_store_id = local.identity_store_id
  user_name         = each.key
  display_name      = "${each.value.given_name} ${each.value.family_name}"

  name {
    given_name  = each.value.given_name
    family_name = each.value.family_name
  }

  emails {
    value   = each.value.email
    type    = "work"
    primary = true
  }
}

resource "aws_identitystore_group_membership" "administrator" {
  provider = aws.identity_center
  for_each = local.identity_center_resources_enabled ? var.administrator_users : {}

  identity_store_id = local.identity_store_id
  group_id          = aws_identitystore_group.administrators[0].group_id
  member_id         = aws_identitystore_user.administrators[each.key].user_id
}

resource "aws_identitystore_group_membership" "operator" {
  provider = aws.identity_center
  for_each = local.identity_center_resources_enabled ? var.administrator_users : {}

  identity_store_id = local.identity_store_id
  group_id          = aws_identitystore_group.operators[0].group_id
  member_id         = aws_identitystore_user.administrators[each.key].user_id
}

resource "aws_ssoadmin_permission_set" "administrator" {
  provider         = aws.identity_center
  count            = local.identity_center_resources_enabled ? 1 : 0
  instance_arn     = local.identity_center_instance_arn
  name             = "Gala-Administrator"
  description      = "Six-hour human-only administration of the Gala AWS Organization and Identity Center."
  session_duration = "PT6H"
}

resource "aws_ssoadmin_managed_policy_attachment" "administrator" {
  provider           = aws.identity_center
  count              = local.identity_center_resources_enabled ? 1 : 0
  instance_arn       = local.identity_center_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.administrator[0].arn
  managed_policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

resource "aws_ssoadmin_permission_set" "operator" {
  provider         = aws.identity_center
  count            = local.identity_center_resources_enabled ? 1 : 0
  instance_arn     = local.identity_center_instance_arn
  name             = "Gala-Operator"
  description      = "Six-hour routine operations. No secret reads, identity mutations, or self-elevation."
  session_duration = "PT6H"
}

resource "aws_ssoadmin_managed_policy_attachment" "operator_read_only" {
  provider           = aws.identity_center
  count              = local.identity_center_resources_enabled ? 1 : 0
  instance_arn       = local.identity_center_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.operator[0].arn
  managed_policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_ssoadmin_permission_set_inline_policy" "operator" {
  provider           = aws.identity_center
  count              = local.identity_center_resources_enabled ? 1 : 0
  instance_arn       = local.identity_center_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.operator[0].arn

  inline_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "OperateGalaDeliveryOnly"
        Effect = "Allow"
        Action = [
          "codebuild:StartBuild",
          "codebuild:StopBuild",
          "codepipeline:StartPipelineExecution",
          "codepipeline:RetryStageExecution",
          "codepipeline:StopPipelineExecution",
          "ssm:SendCommand",
          "ssm:GetCommandInvocation",
          "ssm:ListCommandInvocations",
        ]
        Resource = "*"
      },
      {
        Sid    = "DenyPrivilegeSecretsAndOrganizationMutation"
        Effect = "Deny"
        Action = [
          "account:*",
          "aws-portal:*",
          "billing:*",
          "ce:*",
          "iam:Add*",
          "iam:Attach*",
          "iam:Change*",
          "iam:Create*",
          "iam:Delete*",
          "iam:Detach*",
          "iam:Enable*",
          "iam:Generate*",
          "iam:PassRole",
          "iam:Put*",
          "iam:Remove*",
          "iam:Set*",
          "iam:Tag*",
          "iam:Untag*",
          "iam:Update*",
          "iam:Upload*",
          "identitystore:*",
          "kms:Decrypt",
          "kms:GenerateDataKey*",
          "organizations:*",
          "secretsmanager:GetSecretValue",
          "secretsmanager:PutSecretValue",
          "secretsmanager:UpdateSecret",
          "secretsmanager:DeleteSecret",
          "sso:*",
          "sso-admin:*",
          "sts:AssumeRole*",
        ]
        Resource = "*"
      },
    ]
  })
}

resource "aws_ssoadmin_permission_set" "elevated" {
  provider         = aws.identity_center
  count            = local.identity_center_resources_enabled ? 1 : 0
  instance_arn     = local.identity_center_instance_arn
  name             = "Gala-Elevated"
  description      = "Twelve-hour human-approved elevation for one agreed sensitive operation. PT12H is the AWS-enforced maximum for a permission set's role session."
  session_duration = "PT12H"
}

resource "aws_ssoadmin_managed_policy_attachment" "elevated" {
  provider           = aws.identity_center
  count              = local.identity_center_resources_enabled ? 1 : 0
  instance_arn       = local.identity_center_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.elevated[0].arn
  managed_policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

resource "aws_ssoadmin_account_assignment" "administrator" {
  provider           = aws.identity_center
  count              = local.identity_center_resources_enabled ? 1 : 0
  instance_arn       = local.identity_center_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.administrator[0].arn
  principal_id       = aws_identitystore_group.administrators[0].group_id
  principal_type     = "GROUP"
  target_id          = data.aws_caller_identity.current.account_id
  target_type        = "AWS_ACCOUNT"
}

resource "aws_ssoadmin_account_assignment" "operator" {
  provider           = aws.identity_center
  count              = local.identity_center_resources_enabled ? 1 : 0
  instance_arn       = local.identity_center_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.operator[0].arn
  principal_id       = aws_identitystore_group.operators[0].group_id
  principal_type     = "GROUP"
  target_id          = data.aws_caller_identity.current.account_id
  target_type        = "AWS_ACCOUNT"
}

resource "aws_ssoadmin_account_assignment" "elevated" {
  provider           = aws.identity_center
  count              = local.identity_center_resources_enabled ? 1 : 0
  instance_arn       = local.identity_center_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.elevated[0].arn
  principal_id       = aws_identitystore_group.elevated_operators[0].group_id
  principal_type     = "GROUP"
  target_id          = data.aws_caller_identity.current.account_id
  target_type        = "AWS_ACCOUNT"
}
