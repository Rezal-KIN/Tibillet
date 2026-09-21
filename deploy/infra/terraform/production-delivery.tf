resource "aws_ssm_document" "production_deploy" {
  count           = local.production_resources_enabled ? 1 : 0
  name            = "${local.name_prefix}-production-deploy"
  document_type   = "Command"
  document_format = "JSON"

  content = jsonencode({
    schemaVersion = "2.2"
    description   = "Deploy one approved immutable TiBillet Gala release to its explicitly targeted EC2 instance."
    parameters = {
      ReleaseManifestUri = {
        type           = "String"
        description    = "S3 URI of the immutable release manifest under this Gala's release prefix."
        allowedPattern = "^s3://${aws_s3_bucket.backups[0].bucket}/releases/${var.production_gala_slug}/[A-Za-z0-9._-]+\\.json$"
      }
    }
    mainSteps = [{
      action = "aws:runShellScript"
      name   = "DeployApprovedRelease"
      inputs = {
        runCommand = [
          "/usr/local/lib/tibillet-gala/deploy-release-from-s3.sh /etc/tibillet-gala/${var.production_gala_slug}.conf '{{ ReleaseManifestUri }}'",
        ]
      }
    }]
  })

  lifecycle {
    precondition {
      condition     = var.production_target_instance_id != "" && var.production_gala_slug != ""
      error_message = "production_target_instance_id and production_gala_slug are required when enable_production_pipeline is true."
    }

    precondition {
      condition     = contains(keys(var.galas), var.production_gala_slug)
      error_message = "production_gala_slug must name a declared gala so Terraform can provision its secret and S3 permissions."
    }
  }
}

resource "aws_iam_role" "production_build" {
  count              = local.production_resources_enabled ? 1 : 0
  name               = "${local.name_prefix}-production-build"
  assume_role_policy = data.aws_iam_policy_document.codebuild_assume_role.json
}

data "aws_iam_policy_document" "production_build" {
  count = local.production_resources_enabled ? 1 : 0

  statement {
    sid       = "WriteShortLivedBuildLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.production_deploy[0].arn}:*"]
  }

  statement {
    sid = "WriteOnlyTargetGalaReleaseManifest"
    actions = [
      "s3:PutObject",
      "s3:PutObjectTagging",
    ]
    resources = ["${aws_s3_bucket.backups[0].arn}/releases/${var.production_gala_slug}/*"]
  }

  statement {
    sid = "DeployOnlyToTheTargetGala"
    actions = [
      "ssm:SendCommand",
    ]
    resources = [
      aws_ssm_document.production_deploy[0].arn,
      "arn:${data.aws_partition.current.partition}:ec2:${var.aws_region}:${data.aws_caller_identity.current.account_id}:instance/${var.production_target_instance_id}",
    ]
  }

  statement {
    sid       = "ReadOwnDeploymentCommandStatus"
    actions   = ["ssm:GetCommandInvocation"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "production_build" {
  count  = local.production_resources_enabled ? 1 : 0
  name   = "${local.name_prefix}-production-build"
  role   = aws_iam_role.production_build[0].id
  policy = data.aws_iam_policy_document.production_build[0].json
}

resource "aws_codebuild_project" "production" {
  count          = local.production_resources_enabled ? 1 : 0
  name           = "${local.name_prefix}-production"
  description    = "Manually promotes one reviewed immutable release manifest without rebuilding it."
  service_role   = aws_iam_role.production_build[0].arn
  build_timeout  = 30
  queued_timeout = 60

  artifacts { type = "CODEPIPELINE" }

  environment {
    compute_type                = "BUILD_GENERAL1_SMALL"
    image                       = "aws/codebuild/amazonlinux-x86_64-standard:5.0"
    type                        = "LINUX_CONTAINER"
    privileged_mode             = false
    image_pull_credentials_type = "CODEBUILD"

    environment_variable {
      name  = "EXPECTED_GALA_SLUG"
      value = var.production_gala_slug
    }
    environment_variable {
      name  = "RELEASE_MANIFEST_PATH"
      value = var.production_release_manifest_path
    }
    environment_variable {
      name  = "RELEASE_BUCKET"
      value = aws_s3_bucket.backups[0].bucket
    }
    environment_variable {
      name  = "TARGET_INSTANCE_ID"
      value = var.production_target_instance_id
    }
    environment_variable {
      name  = "DEPLOYMENT_DOCUMENT_NAME"
      value = aws_ssm_document.production_deploy[0].name
    }
  }

  logs_config {
    cloudwatch_logs {
      group_name  = aws_cloudwatch_log_group.production_deploy[0].name
      stream_name = "deploy"
    }
  }

  source {
    type      = "CODEPIPELINE"
    buildspec = file("${path.root}/../../buildspec/tibillet-production.yml")
  }
}

resource "aws_iam_role" "production_pipeline" {
  count = local.production_resources_enabled ? 1 : 0
  name  = "${local.name_prefix}-production-pipeline"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "codepipeline.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

data "aws_iam_policy_document" "production_pipeline" {
  count = local.production_resources_enabled ? 1 : 0

  statement {
    sid       = "UseOnlyGalaGitHubConnection"
    actions   = ["codeconnections:UseConnection", "codestar-connections:UseConnection"]
    resources = [aws_codestarconnections_connection.github[0].arn]
  }

  statement {
    sid       = "RunOnlyGalaProductionBuild"
    actions   = ["codebuild:StartBuild", "codebuild:BatchGetBuilds"]
    resources = [aws_codebuild_project.production[0].arn]
  }

  statement {
    sid = "UseShortLivedArtifacts"
    actions = [
      "s3:GetBucketVersioning",
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:PutObject",
    ]
    resources = [
      aws_s3_bucket.artifacts[0].arn,
      "${aws_s3_bucket.artifacts[0].arn}/*",
    ]
  }
}

resource "aws_iam_role_policy" "production_pipeline" {
  count  = local.production_resources_enabled ? 1 : 0
  name   = "${local.name_prefix}-production-pipeline"
  role   = aws_iam_role.production_pipeline[0].id
  policy = data.aws_iam_policy_document.production_pipeline[0].json
}

resource "aws_codepipeline" "production" {
  count    = local.production_resources_enabled ? 1 : 0
  name     = "${local.name_prefix}-production"
  role_arn = aws_iam_role.production_pipeline[0].arn

  artifact_store {
    location = aws_s3_bucket.artifacts[0].bucket
    type     = "S3"
  }

  stage {
    name = "Source"

    action {
      name             = "ReviewedReleaseManifest"
      category         = "Source"
      owner            = "AWS"
      provider         = "CodeStarSourceConnection"
      version          = "1"
      output_artifacts = ["SourceOutput"]

      configuration = {
        ConnectionArn        = aws_codestarconnections_connection.github[0].arn
        FullRepositoryId     = "${var.github_owner}/${var.github_repository}"
        BranchName           = var.production_source_branch
        DetectChanges        = "false"
        OutputArtifactFormat = "CODEBUILD_CLONE_REF"
      }
    }
  }

  stage {
    name = "ApprovePromotion"

    action {
      name     = "HumanApproval"
      category = "Approval"
      owner    = "AWS"
      provider = "Manual"
      version  = "1"
    }
  }

  stage {
    name = "DeployExactManifest"

    action {
      name            = "UploadAndDeploy"
      category        = "Build"
      owner           = "AWS"
      provider        = "CodeBuild"
      version         = "1"
      input_artifacts = ["SourceOutput"]

      configuration = {
        ProjectName = aws_codebuild_project.production[0].name
      }
    }
  }
}
