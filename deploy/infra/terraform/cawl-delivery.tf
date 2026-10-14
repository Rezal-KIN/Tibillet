# Parallel CAWL delivery chain. It mirrors the Stripe chain (Test on Smoke,
# Foundation, per-Gala Production) without touching it:
#   - CAWL ECR repositories of their own; shared test/live payment secrets;
#   - Test CAWL builds var.cawl_source_branch and deploys gala-smoke-cawl only;
#   - Foundation CAWL creates Galas whose Production pipeline promotes only
#     images proven on gala-smoke-cawl (test-validated-cawl/ markers).
# Foundation enables it once with GalaName "Enable CAWL Platform", which adds
# gala-smoke-cawl to the catalogue; enable_cawl_platform follows from it.

locals {
  cawl_components = toset(["lespass", "fedow", "laboutik"])
  # gala-smoke-cawl joins the deploy-document set like any created Gala.
  test_cawl_enabled = local.cawl_platform_enabled && contains(keys(local.production_deploy_document_galas), local.cawl_smoke_slug)

  gala_payment_secret_arn = local.gala_resources_enabled ? {
    for slug, gala in var.galas : slug => (
      contains(local.smoke_gala_slugs, slug)
      ? aws_secretsmanager_secret.stripe_test[0].arn
      : aws_secretsmanager_secret.stripe_live[0].arn
    )
  } : {}
  cawl_repository_arns = { for component, repo in aws_ecr_repository.cawl : component => repo.arn }
  gala_lespass_repository_arn = {
    for slug, gala in var.galas : slug => (
      gala.payment_provider == "cawl"
      ? lookup(local.cawl_repository_arns, "lespass", null)
      : (local.delivery_resources_enabled ? aws_ecr_repository.lespass[0].arn : null)
    )
  }
  gala_application_repository_arns = {
    for slug, gala in var.galas : slug => (
      gala.payment_provider == "cawl"
      ? [for component in ["fedow", "laboutik"] : local.cawl_repository_arns[component] if contains(keys(local.cawl_repository_arns), component)]
      : [for repo in aws_ecr_repository.applications : repo.arn]
    )
  }
}

# Payment credentials share the existing test/live containers, with separate
# stripe and cawl sections. The versioned Gala configuration selects one.

# --- Images: separate repositories, so CAWL pushes never shorten the
# retention of digests pinned by Stripe Galas (and the reverse). ------------

resource "aws_ecr_repository" "cawl" {
  for_each             = local.delivery_resources_enabled && var.enable_cawl_platform ? local.cawl_components : toset([])
  name                 = "${var.project_name}/cawl/${each.key}"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "cawl" {
  for_each   = aws_ecr_repository.cawl
  repository = each.value.name
  policy     = aws_ecr_lifecycle_policy.lespass[0].policy
}

# --- Test CAWL: build the CAWL branch. -------------------------------------

resource "aws_cloudwatch_log_group" "test_cawl_build" {
  count             = local.test_cawl_enabled ? 1 : 0
  name              = "/aws/codebuild/${local.name_prefix}-test-cawl"
  retention_in_days = var.codebuild_log_retention_days
}

resource "aws_iam_role" "test_cawl_build" {
  count              = local.test_cawl_enabled ? 1 : 0
  name               = "${local.name_prefix}-test-cawl-build"
  assume_role_policy = data.aws_iam_policy_document.codebuild_assume_role.json
}

data "aws_iam_policy_document" "test_cawl_build" {
  count = local.test_cawl_enabled ? 1 : 0

  statement {
    sid       = "WriteShortLivedBuildLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.test_cawl_build[0].arn}:*"]
  }

  statement {
    sid       = "WritePipelineArtifacts"
    actions   = ["s3:GetObject", "s3:GetObjectVersion", "s3:PutObject"]
    resources = ["${aws_s3_bucket.artifacts[0].arn}/*"]
  }

  statement {
    sid = "PublishOnlyCawlApplicationImages"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:DescribeImages",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [for repo in aws_ecr_repository.cawl : repo.arn]
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
    resources = [var.github_connection_arn]
  }
}

resource "aws_iam_role_policy" "test_cawl_build" {
  count  = local.test_cawl_enabled ? 1 : 0
  name   = "${local.name_prefix}-test-cawl-build"
  role   = aws_iam_role.test_cawl_build[0].id
  policy = data.aws_iam_policy_document.test_cawl_build[0].json
}

resource "aws_codebuild_project" "test_cawl" {
  count          = local.test_cawl_enabled ? 1 : 0
  name           = "${local.name_prefix}-test-cawl"
  description    = "Builds the three CAWL applications from one fixed commit of the CAWL branch and publishes immutable ECR digests."
  service_role   = aws_iam_role.test_cawl_build[0].arn
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
    dynamic "environment_variable" {
      for_each = aws_ecr_repository.cawl
      content {
        name  = "${upper(environment_variable.key)}_ECR_REPOSITORY"
        value = environment_variable.value.name
      }
    }
    environment_variable {
      name  = "RELEASE_PLATFORM"
      value = "v1"
    }
  }

  logs_config {
    cloudwatch_logs {
      group_name  = aws_cloudwatch_log_group.test_cawl_build[0].name
      stream_name = "build"
    }
  }

  source {
    type      = "CODEPIPELINE"
    buildspec = file("${path.root}/../../buildspec/tibillet-test.yml")
  }
}

# --- Test CAWL: deploy only to gala-smoke-cawl. ----------------------------

resource "aws_cloudwatch_log_group" "test_cawl_deploy" {
  count             = local.test_cawl_enabled ? 1 : 0
  name              = "/aws/codebuild/${local.name_prefix}-test-cawl-deploy"
  retention_in_days = var.codebuild_log_retention_days
}

resource "aws_iam_role" "test_cawl_deploy" {
  count              = local.test_cawl_enabled ? 1 : 0
  name               = "${local.name_prefix}-test-cawl-deploy"
  assume_role_policy = data.aws_iam_policy_document.codebuild_assume_role.json
}

data "aws_iam_policy_document" "test_cawl_deploy" {
  count = local.test_cawl_enabled ? 1 : 0

  statement {
    sid       = "WriteOnlyTestCawlDeploymentLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.test_cawl_deploy[0].arn}:*"]
  }

  statement {
    sid       = "ReadTestCawlPipelineArtifacts"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${aws_s3_bucket.artifacts[0].arn}/*"]
  }

  statement {
    sid       = "ListOnlyCardUploadFolder"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.backups[0].arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["card-stock/uploads/*"]
    }
  }

  statement {
    sid       = "ReadUploadedAndFrozenCardStock"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.backups[0].arn}/card-stock/*"]
  }

  statement {
    sid       = "PublishOnlyChecksumCardStock"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.backups[0].arn}/card-stock/*.csv"]
  }

  statement {
    sid     = "WriteOnlyCawlSmokeManifests"
    actions = ["s3:PutObject", "s3:GetObject"]
    resources = [
      "${aws_s3_bucket.backups[0].arn}/releases/${local.cawl_smoke_slug}/*",
      "${aws_s3_bucket.backups[0].arn}/${local.smoke_marker_prefix.cawl}/smoke-*.json",
    ]
  }

  statement {
    sid       = "IdentifyAccount"
    actions   = ["sts:GetCallerIdentity"]
    resources = ["*"]
  }

  statement {
    sid = "CloneTestCawlSource"
    actions = [
      "codestar-connections:GetConnectionToken", "codestar-connections:UseConnection",
      "codeconnections:GetConnectionToken", "codeconnections:UseConnection",
    ]
    resources = [var.github_connection_arn]
  }

  statement {
    sid     = "SendOnlyCawlSmokeCommands"
    actions = ["ssm:SendCommand"]
    resources = [
      aws_ssm_document.production_deploy[local.cawl_smoke_slug].arn,
      "arn:${data.aws_partition.current.partition}:ec2:${var.aws_region}:${data.aws_caller_identity.current.account_id}:instance/${module.gala[local.cawl_smoke_slug].instance_id}",
    ]
  }

  statement {
    sid       = "ReadCawlSmokeCommandStatus"
    actions   = ["ssm:GetCommandInvocation"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "test_cawl_deploy" {
  count  = local.test_cawl_enabled ? 1 : 0
  name   = "${local.name_prefix}-test-cawl-deploy"
  role   = aws_iam_role.test_cawl_deploy[0].id
  policy = data.aws_iam_policy_document.test_cawl_deploy[0].json
}

resource "aws_codebuild_project" "test_cawl_deploy" {
  count          = local.test_cawl_enabled ? 1 : 0
  name           = "${local.name_prefix}-test-cawl-deploy"
  description    = "Deploys the fixed CAWL branch commit and digest-pinned stack to only gala-smoke-cawl."
  service_role   = aws_iam_role.test_cawl_deploy[0].arn
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
      value = module.gala[local.cawl_smoke_slug].instance_id
    }
    environment_variable {
      name  = "RELEASE_BUCKET"
      value = aws_s3_bucket.backups[0].bucket
    }
    environment_variable {
      name  = "SMOKE_DEPLOY_DOCUMENT"
      value = aws_ssm_document.production_deploy[local.cawl_smoke_slug].name
    }
    # The Smoke tools derive the manifest prefix and proof marker from it.
    environment_variable {
      name  = "SMOKE_GALA_SLUG"
      value = local.cawl_smoke_slug
    }
  }

  logs_config {
    cloudwatch_logs {
      group_name  = aws_cloudwatch_log_group.test_cawl_deploy[0].name
      stream_name = "deploy"
    }
  }

  source {
    type      = "CODEPIPELINE"
    buildspec = file("${path.root}/../../buildspec/tibillet-test-deploy.yml")
  }
}

# --- Test CAWL pipeline: push on the CAWL branch → build → gala-smoke-cawl. -

resource "aws_iam_role" "test_cawl_pipeline" {
  count = local.test_cawl_enabled ? 1 : 0
  name  = "${local.name_prefix}-test-cawl-pipeline"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "codepipeline.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

data "aws_iam_policy_document" "test_cawl_pipeline" {
  count = local.test_cawl_enabled ? 1 : 0

  statement {
    sid       = "UseOnlyGalaGitHubConnection"
    actions   = ["codeconnections:UseConnection", "codestar-connections:UseConnection"]
    resources = [var.github_connection_arn]
  }

  statement {
    sid       = "RunOnlyGalaTestCawlBuilds"
    actions   = ["codebuild:StartBuild", "codebuild:BatchGetBuilds"]
    resources = [aws_codebuild_project.test_cawl[0].arn, aws_codebuild_project.test_cawl_deploy[0].arn]
  }

  statement {
    sid       = "UseShortLivedArtifacts"
    actions   = ["s3:GetBucketVersioning", "s3:GetObject", "s3:GetObjectVersion", "s3:PutObject"]
    resources = [aws_s3_bucket.artifacts[0].arn, "${aws_s3_bucket.artifacts[0].arn}/*"]
  }
}

resource "aws_iam_role_policy" "test_cawl_pipeline" {
  count  = local.test_cawl_enabled ? 1 : 0
  name   = "${local.name_prefix}-test-cawl-pipeline"
  role   = aws_iam_role.test_cawl_pipeline[0].id
  policy = data.aws_iam_policy_document.test_cawl_pipeline[0].json
}

resource "aws_codepipeline" "test_cawl" {
  count          = local.test_cawl_enabled ? 1 : 0
  name           = "${local.name_prefix}-test-cawl"
  role_arn       = aws_iam_role.test_cawl_pipeline[0].arn
  pipeline_type  = "V2"
  execution_mode = "QUEUED"
  # CodePipeline starts once at creation; let its IAM policies land first.
  depends_on = [
    aws_iam_role_policy.test_cawl_pipeline,
    aws_iam_role_policy.test_cawl_build,
    aws_iam_role_policy.test_cawl_deploy,
  ]

  trigger {
    provider_type = "CodeStarSourceConnection"

    git_configuration {
      source_action_name = "CawlBranch"

      push {
        branches {
          includes = [var.cawl_source_branch]
        }
      }
    }
  }

  artifact_store {
    location = aws_s3_bucket.artifacts[0].bucket
    type     = "S3"
  }

  stage {
    name = "Source"

    action {
      name             = "CawlBranch"
      category         = "Source"
      owner            = "AWS"
      provider         = "CodeStarSourceConnection"
      version          = "1"
      output_artifacts = ["SourceOutput"]

      configuration = {
        ConnectionArn        = var.github_connection_arn
        FullRepositoryId     = "${var.application_github_owner}/${var.application_github_repository}"
        BranchName           = var.cawl_source_branch
        DetectChanges        = "false"
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
        ProjectName = aws_codebuild_project.test_cawl[0].name
      }
    }
  }

  stage {
    name = "DeploySmokeCawl"

    action {
      name            = "DeployFixedCandidate"
      category        = "Build"
      owner           = "AWS"
      provider        = "CodeBuild"
      version         = "1"
      input_artifacts = ["SourceOutput", "BuildOutput"]
      configuration = {
        ProjectName   = aws_codebuild_project.test_cawl_deploy[0].name
        PrimarySource = "SourceOutput"
      }
    }
  }
}

# --- Foundation CAWL: same reviewed Foundation builds, CAWL Gala requests. -

resource "aws_iam_role" "foundation_cawl_pipeline" {
  count = local.foundation_pipeline_enabled && local.test_cawl_enabled ? 1 : 0
  name  = "${local.name_prefix}-foundation-cawl-pipeline"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "codepipeline.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

data "aws_iam_policy_document" "foundation_cawl_pipeline" {
  count = local.foundation_pipeline_enabled && local.test_cawl_enabled ? 1 : 0

  statement {
    sid       = "UseOnlyGalaGitHubConnection"
    actions   = ["codeconnections:UseConnection", "codestar-connections:UseConnection"]
    resources = [var.github_connection_arn]
  }

  statement {
    sid       = "RunOnlyFoundationBuilds"
    actions   = ["codebuild:StartBuild", "codebuild:BatchGetBuilds"]
    resources = [aws_codebuild_project.foundation_plan[0].arn, aws_codebuild_project.foundation_apply[0].arn, aws_codebuild_project.foundation_finalize[0].arn]
  }

  statement {
    sid       = "UseShortLivedArtifacts"
    actions   = ["s3:GetBucketVersioning", "s3:GetObject", "s3:GetObjectVersion", "s3:PutObject"]
    resources = [aws_s3_bucket.artifacts[0].arn, "${aws_s3_bucket.artifacts[0].arn}/*"]
  }
}

resource "aws_iam_role_policy" "foundation_cawl_pipeline" {
  count  = local.foundation_pipeline_enabled && local.test_cawl_enabled ? 1 : 0
  name   = "${local.name_prefix}-foundation-cawl-pipeline"
  role   = aws_iam_role.foundation_cawl_pipeline[0].id
  policy = data.aws_iam_policy_document.foundation_cawl_pipeline[0].json
}

resource "aws_codepipeline" "foundation_cawl" {
  count         = local.foundation_pipeline_enabled && local.test_cawl_enabled ? 1 : 0
  name          = "${local.name_prefix}-foundation-cawl"
  role_arn      = aws_iam_role.foundation_cawl_pipeline[0].arn
  pipeline_type = "V2"
  depends_on    = [aws_iam_role_policy.foundation_cawl_pipeline]

  variable {
    name        = "GalaName"
    description = "Human-readable new CAWL Gala name; Foundation derives its unique technical slug."
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
          { name = "GALA_NAME", value = "#{variables.GalaName}", type = "PLAINTEXT" },
          { name = "PAYMENT_PROVIDER", value = "cawl", type = "PLAINTEXT" },
        ])
      }
    }
  }

  stage {
    name = "ApplyCheckedPlan"
    action {
      name            = "ApplyExactPlan"
      category        = "Build"
      owner           = "AWS"
      provider        = "CodeBuild"
      version         = "1"
      input_artifacts = ["SourceOutput", "PlanOutput"]
      configuration = {
        ProjectName   = aws_codebuild_project.foundation_apply[0].name
        PrimarySource = "SourceOutput"
      }
    }
  }

  stage {
    name = "InitializeGalaSecrets"
    action {
      name            = "InitializeAndRecordCatalog"
      category        = "Build"
      owner           = "AWS"
      provider        = "CodeBuild"
      version         = "1"
      input_artifacts = ["SourceOutput", "PlanOutput"]
      configuration = {
        ProjectName   = aws_codebuild_project.foundation_finalize[0].name
        PrimarySource = "SourceOutput"
        EnvironmentVariables = jsonencode([
          { name = "GALA_NAME", value = "#{variables.GalaName}", type = "PLAINTEXT" },
          { name = "PAYMENT_PROVIDER", value = "cawl", type = "PLAINTEXT" },
        ])
      }
    }
  }
}
