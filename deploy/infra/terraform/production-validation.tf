# Pre-approval validation has no deployment or release-write permissions.
resource "aws_cloudwatch_log_group" "production_validate" {
  for_each          = local.production_target_galas
  name              = "/aws/codebuild/${local.name_prefix}-production-${each.key}-validate"
  retention_in_days = var.codebuild_log_retention_days
}

resource "aws_iam_role" "production_validate" {
  for_each           = local.production_target_galas
  name               = "${local.name_prefix}-production-${each.key}-validate"
  assume_role_policy = data.aws_iam_policy_document.codebuild_assume_role.json
}

data "aws_iam_policy_document" "production_validate" {
  for_each = local.production_target_galas

  statement {
    sid       = "WriteOwnValidationLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.production_validate[each.key].arn}:*"]
  }

  statement {
    sid       = "ReadWritePipelineArtifacts"
    actions   = ["s3:GetObject", "s3:GetObjectVersion", "s3:PutObject"]
    resources = ["${aws_s3_bucket.artifacts[0].arn}/*"]
  }

  statement {
    sid       = "ReadOnlySuccessfulSmokeCandidates"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.backups[0].arn}/test-validated/smoke-*.json"]
  }

  statement {
    sid = "CloneReviewedManifestSource"
    actions = [
      "codestar-connections:GetConnectionToken", "codestar-connections:UseConnection",
      "codeconnections:GetConnectionToken", "codeconnections:UseConnection",
    ]
    resources = [var.github_connection_arn]
  }
}

resource "aws_iam_role_policy" "production_validate" {
  for_each = local.production_target_galas
  name     = "${local.name_prefix}-production-${each.key}-validate"
  role     = aws_iam_role.production_validate[each.key].id
  policy   = data.aws_iam_policy_document.production_validate[each.key].json
}

resource "aws_codebuild_project" "production_validate" {
  for_each       = local.production_target_galas
  name           = "${local.name_prefix}-production-${each.key}-validate"
  description    = "Proves a Gala release exactly matches a successful Smoke deployment before approval."
  service_role   = aws_iam_role.production_validate[each.key].arn
  build_timeout  = 15
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
      value = each.key
    }
    environment_variable {
      name  = "RELEASE_BUCKET"
      value = aws_s3_bucket.backups[0].bucket
    }
  }

  logs_config {
    cloudwatch_logs {
      group_name  = aws_cloudwatch_log_group.production_validate[each.key].name
      stream_name = "validate"
    }
  }

  source {
    type      = "CODEPIPELINE"
    buildspec = file("${path.root}/../../buildspec/tibillet-production-validate.yml")
  }
}
