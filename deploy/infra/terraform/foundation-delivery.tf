# This is the manual entry point for creating a Gala. Its inputs are all public
# infrastructure metadata. The high-privilege CodeBuild role is supplied by an
# administrator, rather than silently granting Terraform-wide permissions to a
# normal delivery role.

resource "aws_iam_role" "foundation_build" {
  count              = var.manage_foundation_codebuild_role ? 1 : 0
  name               = "${local.name_prefix}-foundation-build"
  assume_role_policy = data.aws_iam_policy_document.codebuild_assume_role.json
}

data "aws_iam_policy_document" "foundation_build" {
  count = var.manage_foundation_codebuild_role ? 1 : 0

  statement {
    sid       = "IdentifyTheGalaAccount"
    actions   = ["sts:GetCallerIdentity"]
    resources = ["*"]
  }

  statement {
    sid = "UseOnlyTerraformStateAndGalaBuckets"
    actions = [
      "s3:GetBucketVersioning", "s3:ListBucket", "s3:GetObject", "s3:PutObject", "s3:DeleteObject",
    ]
    resources = [
      "arn:${data.aws_partition.current.partition}:s3:::${var.terraform_state_bucket_name}",
      "arn:${data.aws_partition.current.partition}:s3:::${var.terraform_state_bucket_name}/*",
      aws_s3_bucket.backups[0].arn,
      "${aws_s3_bucket.backups[0].arn}/*",
      aws_s3_bucket.artifacts[0].arn,
      "${aws_s3_bucket.artifacts[0].arn}/*",
    ]
  }

  statement {
    sid = "ManageOnlyGalaNamedStorage"
    actions = [
      "s3:CreateBucket", "s3:DeleteBucket", "s3:GetBucket*", "s3:PutBucket*", "s3:GetEncryptionConfiguration",
      "s3:GetAccelerateConfiguration", "s3:GetLifecycleConfiguration", "s3:GetPublicAccessBlock", "s3:GetReplicationConfiguration", "s3:GetBucketTagging", "s3:PutBucketTagging",
    ]
    resources = ["arn:${data.aws_partition.current.partition}:s3:::${local.name_prefix}-*"]
  }

  statement {
    sid       = "ListBucketsForTerraform"
    actions   = ["s3:ListAllMyBuckets"]
    resources = ["*"]
  }

  statement {
    sid = "ManageParisGalaEc2"
    actions = [
      "ec2:AllocateAddress", "ec2:AssociateAddress", "ec2:AuthorizeSecurityGroupEgress", "ec2:AuthorizeSecurityGroupIngress",
      "ec2:CreateSecurityGroup", "ec2:CreateTags", "ec2:DeleteSecurityGroup", "ec2:DeleteTags", "ec2:Describe*",
      "ec2:DisassociateAddress", "ec2:ModifyInstanceAttribute", "ec2:ReleaseAddress", "ec2:RevokeSecurityGroupEgress",
      "ec2:RevokeSecurityGroupIngress", "ec2:RunInstances", "ec2:TerminateInstances",
    ]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }
  }

  statement {
    sid = "ManageOnlyGalaIamRoles"
    actions = [
      "iam:AttachRolePolicy", "iam:CreateInstanceProfile", "iam:CreateRole", "iam:DeleteInstanceProfile", "iam:DeleteRole",
      "iam:DeleteRolePolicy", "iam:DetachRolePolicy", "iam:GetInstanceProfile", "iam:GetRole", "iam:GetRolePolicy",
      "iam:ListAttachedRolePolicies", "iam:ListRolePolicies", "iam:PutRolePolicy", "iam:RemoveRoleFromInstanceProfile", "iam:AddRoleToInstanceProfile", "iam:TagRole",
      "iam:TagInstanceProfile", "iam:UntagInstanceProfile", "iam:UntagRole", "iam:UpdateAssumeRolePolicy",
    ]
    resources = [
      "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:role/${local.name_prefix}-*",
      "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:instance-profile/${local.name_prefix}-*",
      # Gala EC2 roles deliberately omit the environment segment (for example
      # tibillet-gala-paris-gala-smoke-ec2), but remain confined to this project.
      "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:role/${var.project_name}-gala-*-*",
      "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:instance-profile/${var.project_name}-gala-*-*",
    ]
  }

  statement {
    sid     = "PassOnlyGalaServiceRoles"
    actions = ["iam:PassRole"]
    resources = [
      "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:role/${local.name_prefix}-*",
      "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:role/${var.project_name}-gala-*-*",
    ]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ec2.amazonaws.com", "codebuild.amazonaws.com", "codepipeline.amazonaws.com"]
    }
  }

  statement {
    sid = "ManageOnlyGalaSecrets"
    actions = [
      "secretsmanager:CreateSecret", "secretsmanager:DeleteSecret", "secretsmanager:DescribeSecret", "secretsmanager:ListSecretVersionIds",
      # Terraform reads a secret resource policy while refreshing state. This
      # deliberately excludes secretsmanager:GetSecretValue.
      "secretsmanager:GetResourcePolicy", "secretsmanager:TagResource", "secretsmanager:UntagResource", "secretsmanager:UpdateSecret",
    ]
    resources = ["arn:${data.aws_partition.current.partition}:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${var.project_name}/galas/*"]
  }

  statement {
    sid       = "ListSecretsForTerraform"
    actions   = ["secretsmanager:ListSecrets"]
    resources = ["*"]
  }

  # DescribeLogGroups does not support a log-group resource ARN. It is a
  # read-only discovery call Terraform makes before refreshing the two named
  # Foundation log groups.
  statement {
    sid       = "DiscoverLogGroupsForTerraform"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["*"]
  }

  statement {
    sid = "ManageOnlyGalaDeliveryResources"
    actions = [
      "codebuild:*", "codepipeline:*", "ecr:*", "logs:*", "ssm:AddTagsToResource", "ssm:CreateDocument",
      "ssm:DeleteDocument", "ssm:DescribeDocument", "ssm:DescribeDocumentPermission", "ssm:GetDocument", "ssm:ListDocumentVersions", "ssm:ModifyDocumentPermission",
      "ssm:UpdateDocument",
    ]
    resources = [
      "arn:${data.aws_partition.current.partition}:codebuild:${var.aws_region}:${data.aws_caller_identity.current.account_id}:project/${local.name_prefix}-*",
      "arn:${data.aws_partition.current.partition}:codepipeline:${var.aws_region}:${data.aws_caller_identity.current.account_id}:${local.name_prefix}-*",
      "arn:${data.aws_partition.current.partition}:ecr:${var.aws_region}:${data.aws_caller_identity.current.account_id}:repository/${var.project_name}/*",
      "arn:${data.aws_partition.current.partition}:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/codebuild/${local.name_prefix}-*",
      "arn:${data.aws_partition.current.partition}:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:document/${local.name_prefix}-*",
    ]
  }

  statement {
    sid       = "UseOnlyApprovedGitHubConnection"
    actions   = ["codeconnections:GetConnection", "codeconnections:PassConnection", "codeconnections:UseConnection", "codestar-connections:GetConnection", "codestar-connections:PassConnection", "codestar-connections:UseConnection"]
    resources = [var.github_connection_arn]
  }
}

resource "aws_iam_role_policy" "foundation_build" {
  count  = var.manage_foundation_codebuild_role ? 1 : 0
  name   = "${local.name_prefix}-foundation-build"
  role   = aws_iam_role.foundation_build[0].id
  policy = data.aws_iam_policy_document.foundation_build[0].json
}

resource "aws_cloudwatch_log_group" "foundation_plan" {
  count             = local.foundation_pipeline_enabled ? 1 : 0
  name              = "/aws/codebuild/${local.name_prefix}-foundation-plan"
  retention_in_days = var.codebuild_log_retention_days
}

resource "aws_cloudwatch_log_group" "foundation_apply" {
  count             = local.foundation_pipeline_enabled ? 1 : 0
  name              = "/aws/codebuild/${local.name_prefix}-foundation-apply"
  retention_in_days = var.codebuild_log_retention_days
}

resource "aws_codebuild_project" "foundation_plan" {
  count          = local.foundation_pipeline_enabled ? 1 : 0
  name           = "${local.name_prefix}-foundation-plan"
  description    = "Validates a new Gala request and produces an exact Terraform plan; no AWS resources are changed."
  service_role   = local.foundation_codebuild_role_arn
  build_timeout  = 45
  queued_timeout = 60

  artifacts { type = "CODEPIPELINE" }

  environment {
    compute_type                = "BUILD_GENERAL1_SMALL"
    image                       = "aws/codebuild/amazonlinux-x86_64-standard:5.0"
    type                        = "LINUX_CONTAINER"
    privileged_mode             = false
    image_pull_credentials_type = "CODEBUILD"

    environment_variable {
      name  = "TERRAFORM_STATE_BUCKET"
      value = var.terraform_state_bucket_name
    }
    environment_variable {
      name  = "TERRAFORM_STATE_KEY"
      value = var.terraform_state_key
    }
    environment_variable {
      name  = "FOUNDATION_CODEBUILD_ROLE_ARN"
      value = local.foundation_codebuild_role_arn
    }
    environment_variable {
      name  = "MANAGE_FOUNDATION_CODEBUILD_ROLE"
      value = tostring(var.manage_foundation_codebuild_role)
    }
    environment_variable {
      name  = "FOUNDATION_CATALOG_URI"
      value = "s3://${aws_s3_bucket.backups[0].bucket}/foundation-inputs/galas.json"
    }
    environment_variable {
      name  = "GITHUB_CONNECTION_ARN"
      value = var.github_connection_arn
    }
  }

  logs_config {
    cloudwatch_logs {
      group_name  = aws_cloudwatch_log_group.foundation_plan[0].name
      stream_name = "plan"
    }
  }

  source {
    type      = "CODEPIPELINE"
    buildspec = file("${path.root}/../../buildspec/tibillet-foundation-plan.yml")
  }

  lifecycle {
    precondition {
      condition     = local.foundation_codebuild_role_arn != "" && var.terraform_state_bucket_name != ""
      error_message = "A Foundation CodeBuild role (managed or supplied) and terraform_state_bucket_name are required to create the infrastructure pipeline."
    }
  }
}

resource "aws_codebuild_project" "foundation_apply" {
  count          = local.foundation_pipeline_enabled ? 1 : 0
  name           = "${local.name_prefix}-foundation-apply"
  description    = "Applies only the reviewed Terraform plan from the preceding foundation stage."
  service_role   = local.foundation_codebuild_role_arn
  build_timeout  = 45
  queued_timeout = 60

  artifacts { type = "CODEPIPELINE" }

  environment {
    compute_type                = "BUILD_GENERAL1_SMALL"
    image                       = "aws/codebuild/amazonlinux-x86_64-standard:5.0"
    type                        = "LINUX_CONTAINER"
    privileged_mode             = false
    image_pull_credentials_type = "CODEBUILD"

    environment_variable {
      name  = "TERRAFORM_STATE_BUCKET"
      value = var.terraform_state_bucket_name
    }
    environment_variable {
      name  = "TERRAFORM_STATE_KEY"
      value = var.terraform_state_key
    }
    environment_variable {
      name  = "FOUNDATION_CATALOG_URI"
      value = "s3://${aws_s3_bucket.backups[0].bucket}/foundation-inputs/galas.json"
    }
  }

  logs_config {
    cloudwatch_logs {
      group_name  = aws_cloudwatch_log_group.foundation_apply[0].name
      stream_name = "apply"
    }
  }

  source {
    type      = "CODEPIPELINE"
    buildspec = file("${path.root}/../../buildspec/tibillet-foundation-apply.yml")
  }
}

resource "aws_iam_role" "foundation_pipeline" {
  count = local.foundation_pipeline_enabled ? 1 : 0
  name  = "${local.name_prefix}-foundation-pipeline"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "codepipeline.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

data "aws_iam_policy_document" "foundation_pipeline" {
  count = local.foundation_pipeline_enabled ? 1 : 0

  statement {
    sid       = "UseOnlyGalaGitHubConnection"
    actions   = ["codeconnections:UseConnection", "codestar-connections:UseConnection"]
    resources = [var.github_connection_arn]
  }

  statement {
    sid       = "RunOnlyFoundationBuilds"
    actions   = ["codebuild:StartBuild", "codebuild:BatchGetBuilds"]
    resources = [aws_codebuild_project.foundation_plan[0].arn, aws_codebuild_project.foundation_apply[0].arn]
  }

  statement {
    sid       = "UseShortLivedArtifacts"
    actions   = ["s3:GetBucketVersioning", "s3:GetObject", "s3:GetObjectVersion", "s3:PutObject"]
    resources = [aws_s3_bucket.artifacts[0].arn, "${aws_s3_bucket.artifacts[0].arn}/*"]
  }
}

resource "aws_iam_role_policy" "foundation_pipeline" {
  count  = local.foundation_pipeline_enabled ? 1 : 0
  name   = "${local.name_prefix}-foundation-pipeline"
  role   = aws_iam_role.foundation_pipeline[0].id
  policy = data.aws_iam_policy_document.foundation_pipeline[0].json
}

resource "aws_codepipeline" "foundation" {
  count         = local.foundation_pipeline_enabled ? 1 : 0
  name          = "${local.name_prefix}-foundation"
  role_arn      = aws_iam_role.foundation_pipeline[0].arn
  pipeline_type = "V2"

  variable {
    name        = "GalaSlug"
    description = "New lowercase Gala slug, for example gala-marseille. Existing slugs are rejected."
  }
  variable {
    name        = "GalaDomain"
    description = "Public Lespass apex domain for the new Gala. This value is not a secret."
  }
  variable {
    name          = "InstanceType"
    default_value = "t3.medium"
    description   = "One of t3.small, t3.medium, t3.large, or t3.xlarge."
  }
  variable {
    name          = "RootVolumeSizeGib"
    default_value = "40"
    description   = "Encrypted EC2 root-volume size, between 40 and 512 GiB."
  }
  variable {
    name        = "VpcId"
    description = "Approved Paris VPC ID. It must match the existing Gala catalog after its first execution."
  }
  variable {
    name        = "SubnetId"
    description = "Approved public Paris subnet ID. It must match the existing Gala catalog after its first execution."
  }
  variable {
    name        = "Ec2AmiId"
    description = "Explicit approved Ubuntu AMI ID. It must match the existing Gala catalog after its first execution."
  }
  variable {
    name          = "SshEmergencyCidrs"
    default_value = "disabled"
    description   = "Optional comma-separated emergency SSH CIDRs; use disabled when no SSH ingress is needed."
  }

  artifact_store {
    location = aws_s3_bucket.artifacts[0].bucket
    type     = "S3"
  }

  stage {
    name = "Source"

    action {
      name             = "InfrastructureSource"
      category         = "Source"
      owner            = "AWS"
      provider         = "CodeStarSourceConnection"
      version          = "1"
      output_artifacts = ["SourceOutput"]

      configuration = {
        ConnectionArn        = var.github_connection_arn
        FullRepositoryId     = "${var.github_owner}/${var.github_repository}"
        BranchName           = var.production_source_branch
        DetectChanges        = "false"
        OutputArtifactFormat = "CODEBUILD_CLONE_REF"
      }
    }
  }

  stage {
    name = "PlanNewGala"

    action {
      name             = "ValidateAndPlan"
      category         = "Build"
      owner            = "AWS"
      provider         = "CodeBuild"
      version          = "1"
      input_artifacts  = ["SourceOutput"]
      output_artifacts = ["PlanOutput"]

      configuration = {
        ProjectName = aws_codebuild_project.foundation_plan[0].name
        EnvironmentVariables = jsonencode([
          { name = "GALA_SLUG", value = "#{variables.GalaSlug}", type = "PLAINTEXT" },
          { name = "GALA_DOMAIN", value = "#{variables.GalaDomain}", type = "PLAINTEXT" },
          { name = "INSTANCE_TYPE", value = "#{variables.InstanceType}", type = "PLAINTEXT" },
          { name = "ROOT_VOLUME_SIZE_GIB", value = "#{variables.RootVolumeSizeGib}", type = "PLAINTEXT" },
          { name = "VPC_ID", value = "#{variables.VpcId}", type = "PLAINTEXT" },
          { name = "SUBNET_ID", value = "#{variables.SubnetId}", type = "PLAINTEXT" },
          { name = "EC2_AMI_ID", value = "#{variables.Ec2AmiId}", type = "PLAINTEXT" },
          { name = "SSH_EMERGENCY_CIDRS", value = "#{variables.SshEmergencyCidrs}", type = "PLAINTEXT" },
        ])
      }
    }
  }

  stage {
    name = "ApproveInfrastructure"

    action {
      name     = "ReviewExactPlan"
      category = "Approval"
      owner    = "AWS"
      provider = "Manual"
      version  = "1"
      configuration = {
        CustomData = "Review foundation-plan.txt and foundation.auto.tfvars.json from PlanOutput. Approval applies that exact plan only."
      }
    }
  }

  stage {
    name = "ApplyApprovedPlan"

    action {
      name            = "ApplyExactPlan"
      category        = "Build"
      owner           = "AWS"
      provider        = "CodeBuild"
      version         = "1"
      input_artifacts = ["SourceOutput", "PlanOutput"]

      configuration = {
        # CodeBuild needs an explicit primary source when it receives the
        # repository clone and the reviewed plan as two separate artifacts.
        # The plan remains available as CODEBUILD_SRC_DIR_PlanOutput.
        ProjectName   = aws_codebuild_project.foundation_apply[0].name
        PrimarySource = "SourceOutput"
      }
    }
  }
}
