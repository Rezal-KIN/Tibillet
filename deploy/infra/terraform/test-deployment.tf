# Test is a single shared host. Its build role may deploy only to gala-smoke.
locals {
  test_deploy_enabled = local.production_resources_enabled && contains(keys(local.production_deploy_document_galas), "gala-smoke")
}

resource "aws_cloudwatch_log_group" "test_deploy" {
  count             = local.test_deploy_enabled ? 1 : 0
  name              = "/aws/codebuild/${local.name_prefix}-test-deploy"
  retention_in_days = var.codebuild_log_retention_days
}

resource "aws_iam_role" "test_deploy" {
  count              = local.test_deploy_enabled ? 1 : 0
  name               = "${local.name_prefix}-test-deploy"
  assume_role_policy = data.aws_iam_policy_document.codebuild_assume_role.json
}

data "aws_iam_policy_document" "test_deploy" {
  count = local.test_deploy_enabled ? 1 : 0

  statement {
    sid       = "WriteOnlyTestDeploymentLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.test_deploy[0].arn}:*"]
  }

  statement {
    sid       = "ReadTestPipelineArtifacts"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${aws_s3_bucket.artifacts[0].arn}/*"]
  }

  statement {
    sid     = "WriteOnlySmokeManifests"
    actions = ["s3:PutObject", "s3:GetObject"]
    resources = [
      "${aws_s3_bucket.backups[0].arn}/releases/gala-smoke/*",
      "${aws_s3_bucket.backups[0].arn}/test-validated/smoke-*.json",
    ]
  }

  statement {
    sid       = "IdentifyAccount"
    actions   = ["sts:GetCallerIdentity"]
    resources = ["*"]
  }

  statement {
    sid = "CloneTestSource"
    actions = [
      "codestar-connections:GetConnectionToken", "codestar-connections:UseConnection",
      "codeconnections:GetConnectionToken", "codeconnections:UseConnection",
    ]
    resources = [var.github_connection_arn]
  }

  statement {
    sid     = "SendOnlySmokeCommands"
    actions = ["ssm:SendCommand"]
    resources = [
      aws_ssm_document.production_deploy["gala-smoke"].arn,
      "arn:${data.aws_partition.current.partition}:ec2:${var.aws_region}:${data.aws_caller_identity.current.account_id}:instance/${module.gala["gala-smoke"].instance_id}",
    ]
  }

  statement {
    sid       = "ReadSmokeCommandStatus"
    actions   = ["ssm:GetCommandInvocation"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "test_deploy" {
  count  = local.test_deploy_enabled ? 1 : 0
  name   = "${local.name_prefix}-test-deploy"
  role   = aws_iam_role.test_deploy[0].id
  policy = data.aws_iam_policy_document.test_deploy[0].json
}

resource "aws_codebuild_project" "test_deploy" {
  count          = local.test_deploy_enabled ? 1 : 0
  name           = "${local.name_prefix}-test-deploy"
  description    = "Deploys the fixed main commit and digest-pinned stack to only gala-smoke."
  service_role   = aws_iam_role.test_deploy[0].arn
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
      name  = "SMOKE_INSTANCE_ID"
      value = module.gala["gala-smoke"].instance_id
    }
    environment_variable {
      name  = "RELEASE_BUCKET"
      value = aws_s3_bucket.backups[0].bucket
    }
    environment_variable {
      name  = "SMOKE_DEPLOY_DOCUMENT"
      value = aws_ssm_document.production_deploy["gala-smoke"].name
    }
  }

  logs_config {
    cloudwatch_logs {
      group_name  = aws_cloudwatch_log_group.test_deploy[0].name
      stream_name = "deploy"
    }
  }

  source {
    type      = "CODEPIPELINE"
    buildspec = file("${path.root}/../../buildspec/tibillet-test-deploy.yml")
  }
}
