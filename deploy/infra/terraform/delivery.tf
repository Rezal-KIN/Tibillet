# Delivery resources are opt-in. They cannot exist until a named human has
# approved the GitHub CodeStar connection in the independent Gala account.
resource "aws_codestarconnections_connection" "github" {
  count         = local.delivery_resources_enabled ? 1 : 0
  name          = "${local.name_prefix}-github"
  provider_type = "GitHub"
}

resource "aws_ecr_repository" "lespass" {
  count                = local.delivery_resources_enabled ? 1 : 0
  name                 = "${var.project_name}/lespass"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "lespass" {
  count      = local.delivery_resources_enabled ? 1 : 0
  repository = aws_ecr_repository.lespass[0].name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep a small set of immutable tagged releases"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["sha-"]
          countType     = "imageCountMoreThan"
          countNumber   = var.ecr_release_retention_count
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Remove untagged layers after one week"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = { type = "expire" }
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "test_build" {
  count             = local.delivery_resources_enabled ? 1 : 0
  name              = "/aws/codebuild/${local.name_prefix}-test"
  retention_in_days = var.codebuild_log_retention_days
}

resource "aws_cloudwatch_log_group" "production_deploy" {
  count             = local.production_resources_enabled ? 1 : 0
  name              = "/aws/codebuild/${local.name_prefix}-production"
  retention_in_days = var.codebuild_log_retention_days
}

data "aws_iam_policy_document" "codebuild_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["codebuild.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "test_build" {
  count              = local.delivery_resources_enabled ? 1 : 0
  name               = "${local.name_prefix}-test-build"
  assume_role_policy = data.aws_iam_policy_document.codebuild_assume_role.json
}

data "aws_iam_policy_document" "test_build" {
  count = local.delivery_resources_enabled ? 1 : 0

  statement {
    sid       = "WriteShortLivedBuildLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.test_build[0].arn}:*"]
  }

  statement {
    sid = "WritePipelineArtifacts"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:PutObject",
    ]
    resources = ["${aws_s3_bucket.artifacts[0].arn}/*"]
  }

  statement {
    sid = "PublishOnlyLespassImages"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:DescribeImages",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [aws_ecr_repository.lespass[0].arn]
  }

  statement {
    sid       = "GetEcrAuthorizationToken"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "CloneSourceViaGalaGitHubConnection"
    actions = [
      "codestar-connections:GetConnectionToken",
      "codestar-connections:UseConnection",
      "codeconnections:GetConnectionToken",
      "codeconnections:UseConnection",
    ]
    resources = [aws_codestarconnections_connection.github[0].arn]
  }
}

resource "aws_iam_role_policy" "test_build" {
  count  = local.delivery_resources_enabled ? 1 : 0
  name   = "${local.name_prefix}-test-build"
  role   = aws_iam_role.test_build[0].id
  policy = data.aws_iam_policy_document.test_build[0].json
}

resource "aws_codebuild_project" "test" {
  count          = local.delivery_resources_enabled ? 1 : 0
  name           = "${local.name_prefix}-test"
  description    = "Builds one fixed Lespass fork commit and publishes an immutable ECR digest."
  service_role   = aws_iam_role.test_build[0].arn
  build_timeout  = 45
  queued_timeout = 60

  artifacts { type = "CODEPIPELINE" }

  environment {
    compute_type                = "BUILD_GENERAL1_SMALL"
    image                       = "aws/codebuild/amazonlinux-x86_64-standard:5.0"
    type                        = "LINUX_CONTAINER"
    privileged_mode             = true
    image_pull_credentials_type = "CODEBUILD"

    environment_variable {
      name  = "AWS_ACCOUNT_ID"
      value = data.aws_caller_identity.current.account_id
    }
    environment_variable {
      name  = "LESPASS_ECR_REPOSITORY"
      value = aws_ecr_repository.lespass[0].name
    }
    environment_variable {
      name  = "RELEASE_PLATFORM"
      value = "v1"
    }
  }

  logs_config {
    cloudwatch_logs {
      group_name  = aws_cloudwatch_log_group.test_build[0].name
      stream_name = "build"
    }
  }

  source {
    type      = "CODEPIPELINE"
    buildspec = file("${path.root}/../../buildspec/tibillet-test.yml")
  }
}

resource "aws_iam_role" "test_pipeline" {
  count = local.delivery_resources_enabled ? 1 : 0
  name  = "${local.name_prefix}-test-pipeline"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "codepipeline.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

data "aws_iam_policy_document" "test_pipeline" {
  count = local.delivery_resources_enabled ? 1 : 0

  statement {
    sid       = "UseOnlyGalaGitHubConnection"
    actions   = ["codeconnections:UseConnection", "codestar-connections:UseConnection"]
    resources = [aws_codestarconnections_connection.github[0].arn]
  }

  statement {
    sid       = "RunOnlyGalaTestBuild"
    actions   = ["codebuild:StartBuild", "codebuild:BatchGetBuilds"]
    resources = [aws_codebuild_project.test[0].arn]
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

resource "aws_iam_role_policy" "test_pipeline" {
  count  = local.delivery_resources_enabled ? 1 : 0
  name   = "${local.name_prefix}-test-pipeline"
  role   = aws_iam_role.test_pipeline[0].id
  policy = data.aws_iam_policy_document.test_pipeline[0].json
}

resource "aws_codepipeline" "test" {
  count    = local.delivery_resources_enabled ? 1 : 0
  name     = "${local.name_prefix}-test"
  role_arn = aws_iam_role.test_pipeline[0].arn

  artifact_store {
    location = aws_s3_bucket.artifacts[0].bucket
    type     = "S3"
  }

  stage {
    name = "Source"

    action {
      name             = "LespassFork"
      category         = "Source"
      owner            = "AWS"
      provider         = "CodeStarSourceConnection"
      version          = "1"
      output_artifacts = ["SourceOutput"]

      configuration = {
        ConnectionArn        = aws_codestarconnections_connection.github[0].arn
        FullRepositoryId     = "${var.application_github_owner}/${var.application_github_repository}"
        BranchName           = var.test_source_branch
        DetectChanges        = "true"
        OutputArtifactFormat = "CODEBUILD_CLONE_REF"
      }
    }
  }

  stage {
    name = "BuildAndPublishCandidate"

    action {
      name             = "BuildFixedCommit"
      category         = "Build"
      owner            = "AWS"
      provider         = "CodeBuild"
      version          = "1"
      input_artifacts  = ["SourceOutput"]
      output_artifacts = ["BuildOutput"]

      configuration = {
        ProjectName = aws_codebuild_project.test[0].name
      }
    }
  }
}
