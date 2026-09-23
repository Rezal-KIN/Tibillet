# This is the manual entry point for creating a Gala. Its inputs are all public
# infrastructure metadata. The high-privilege CodeBuild role is supplied by an
# administrator, rather than silently granting Terraform-wide permissions to a
# normal delivery role.

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
  service_role   = var.foundation_codebuild_role_arn
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
      value = var.foundation_codebuild_role_arn
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
      condition     = var.foundation_codebuild_role_arn != "" && var.terraform_state_bucket_name != ""
      error_message = "foundation_codebuild_role_arn and terraform_state_bucket_name are required to create the infrastructure pipeline."
    }
  }
}

resource "aws_codebuild_project" "foundation_apply" {
  count          = local.foundation_pipeline_enabled ? 1 : 0
  name           = "${local.name_prefix}-foundation-apply"
  description    = "Applies only the reviewed Terraform plan from the preceding foundation stage."
  service_role   = var.foundation_codebuild_role_arn
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
    default_value = ""
    description   = "Optional comma-separated emergency SSH CIDRs; never use 0.0.0.0/0."
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
        ProjectName = aws_codebuild_project.foundation_apply[0].name
      }
    }
  }
}
