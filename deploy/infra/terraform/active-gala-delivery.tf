# A fourth, manually started pipeline owns the traffic switch. Production
# pipelines only deploy their own EC2; they cannot claim the shared EIP.
locals {
  active_switch_stages = local.delivery_resources_enabled ? toset(["plan", "apply"]) : toset([])
  active_switch_enis = compact([
    for gala in module.gala : gala.primary_eni_id
  ])
  active_switch_instances = compact([
    for gala in module.gala : gala.instance_id
  ])
}

resource "aws_cloudwatch_log_group" "active_switch" {
  for_each          = local.active_switch_stages
  name              = "/aws/codebuild/${local.name_prefix}-active-gala-${each.key}"
  retention_in_days = var.codebuild_log_retention_days
}

resource "aws_iam_role" "active_switch_build" {
  for_each           = local.active_switch_stages
  name               = "${local.name_prefix}-active-gala-${each.key}-build"
  assume_role_policy = data.aws_iam_policy_document.codebuild_assume_role.json
}

data "aws_iam_policy_document" "active_switch_build" {
  for_each = local.active_switch_stages

  statement {
    sid       = "WriteOnlyOwnBuildLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.active_switch[each.key].arn}:*"]
  }

  statement {
    sid       = "ReadPipelineArtifacts"
    actions   = ["s3:GetObject", "s3:GetObjectVersion", "s3:PutObject"]
    resources = ["${aws_s3_bucket.artifacts[0].arn}/*"]
  }

  statement {
    sid       = "ReadOnlyGalaCatalog"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.backups[0].arn}/foundation-inputs/galas.json"]
  }

  statement {
    sid = "CloneReviewedSource"
    actions = [
      "codestar-connections:GetConnectionToken", "codestar-connections:UseConnection",
      "codeconnections:GetConnectionToken", "codeconnections:UseConnection",
    ]
    resources = [var.github_connection_arn]
  }

  statement {
    sid       = "IdentifyAccount"
    actions   = ["sts:GetCallerIdentity"]
    resources = ["*"]
  }

  statement {
    sid = "InspectOnlyGalaPlacement"
    actions = [
      "ec2:DescribeAddresses", "ec2:DescribeInstances", "ec2:DescribeNetworkInterfaces",
      "ssm:DescribeInstanceInformation",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "ReadActiveGalaMarker"
    actions   = ["ssm:GetParameter"]
    resources = [aws_ssm_parameter.active_gala[0].arn]
  }

  dynamic "statement" {
    for_each = each.key == "apply" ? [1] : []
    content {
      sid     = "MoveOnlyTheSharedGalaEip"
      actions = ["ec2:AssociateAddress"]
      resources = concat(
        ["arn:${data.aws_partition.current.partition}:ec2:${var.aws_region}:${data.aws_caller_identity.current.account_id}:elastic-ip/${aws_eip.shared_public[0].id}"],
        [for eni in local.active_switch_enis : "arn:${data.aws_partition.current.partition}:ec2:${var.aws_region}:${data.aws_caller_identity.current.account_id}:network-interface/${eni}"],
      )
    }
  }

  dynamic "statement" {
    for_each = each.key == "apply" ? [1] : []
    content {
      sid     = "ChangeOnlyKnownGalaNetworkInterfaces"
      actions = ["ec2:ModifyNetworkInterfaceAttribute"]
      resources = [
        for eni in local.active_switch_enis :
        "arn:${data.aws_partition.current.partition}:ec2:${var.aws_region}:${data.aws_caller_identity.current.account_id}:network-interface/${eni}"
      ]
    }
  }

  dynamic "statement" {
    for_each = each.key == "apply" ? [1] : []
    content {
      sid     = "RunReadOnlyTargetHealthcheck"
      actions = ["ssm:SendCommand"]
      resources = concat(
        ["arn:${data.aws_partition.current.partition}:ssm:${var.aws_region}::document/AWS-RunShellScript"],
        [for id in local.active_switch_instances : "arn:${data.aws_partition.current.partition}:ec2:${var.aws_region}:${data.aws_caller_identity.current.account_id}:instance/${id}"],
      )
    }
  }

  dynamic "statement" {
    for_each = each.key == "apply" ? [1] : []
    content {
      sid       = "ReadTargetHealthcheckStatus"
      actions   = ["ssm:GetCommandInvocation"]
      resources = ["*"]
    }
  }

  dynamic "statement" {
    for_each = each.key == "apply" ? [1] : []
    content {
      sid       = "RecordOnlyActiveGalaMarker"
      actions   = ["ssm:PutParameter"]
      resources = [aws_ssm_parameter.active_gala[0].arn]
    }
  }
}

resource "aws_iam_role_policy" "active_switch_build" {
  for_each = local.active_switch_stages
  name     = "${local.name_prefix}-active-gala-${each.key}-build"
  role     = aws_iam_role.active_switch_build[each.key].id
  policy   = data.aws_iam_policy_document.active_switch_build[each.key].json
}

resource "aws_codebuild_project" "active_switch" {
  for_each       = local.active_switch_stages
  name           = "${local.name_prefix}-active-gala-${each.key}"
  description    = "${each.key} the reviewed switch of the single public Gala EIP."
  service_role   = aws_iam_role.active_switch_build[each.key].arn
  build_timeout  = each.key == "apply" ? 15 : 10
  queued_timeout = 60

  artifacts { type = "CODEPIPELINE" }

  environment {
    compute_type                = "BUILD_GENERAL1_SMALL"
    image                       = "aws/codebuild/amazonlinux-x86_64-standard:5.0"
    type                        = "LINUX_CONTAINER"
    privileged_mode             = false
    image_pull_credentials_type = "CODEBUILD"

    environment_variable {
      name  = "GALA_PROJECT_NAME"
      value = var.project_name
    }
    environment_variable {
      name  = "FOUNDATION_CATALOG_URI"
      value = "s3://${aws_s3_bucket.backups[0].bucket}/foundation-inputs/galas.json"
    }
    environment_variable {
      name  = "SHARED_EIP_ALLOCATION_ID"
      value = aws_eip.shared_public[0].id
    }
    environment_variable {
      name  = "PUBLIC_SECURITY_GROUP_ID"
      value = aws_security_group.active_public[0].id
    }
    environment_variable {
      name  = "ACTIVE_GALA_PARAMETER"
      value = aws_ssm_parameter.active_gala[0].name
    }
    environment_variable {
      name  = "SHARED_GALA_DOMAIN"
      value = var.shared_public_domain
    }
  }

  logs_config {
    cloudwatch_logs {
      group_name  = aws_cloudwatch_log_group.active_switch[each.key].name
      stream_name = each.key
    }
  }

  source {
    type      = "CODEPIPELINE"
    buildspec = file("${path.root}/../../buildspec/tibillet-active-gala-${each.key}.yml")
  }
}

resource "aws_iam_role" "active_switch_pipeline" {
  count = local.delivery_resources_enabled ? 1 : 0
  name  = "${local.name_prefix}-active-gala-pipeline"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "codepipeline.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

data "aws_iam_policy_document" "active_switch_pipeline" {
  count = local.delivery_resources_enabled ? 1 : 0

  statement {
    sid       = "UseOnlyApprovedSource"
    actions   = ["codeconnections:UseConnection", "codestar-connections:UseConnection"]
    resources = [var.github_connection_arn]
  }

  statement {
    sid       = "RunOnlyActiveGalaBuilds"
    actions   = ["codebuild:StartBuild", "codebuild:BatchGetBuilds"]
    resources = [for stage in ["plan", "apply"] : aws_codebuild_project.active_switch[stage].arn]
  }

  statement {
    sid       = "UseShortLivedArtifacts"
    actions   = ["s3:GetBucketVersioning", "s3:GetObject", "s3:GetObjectVersion", "s3:PutObject"]
    resources = [aws_s3_bucket.artifacts[0].arn, "${aws_s3_bucket.artifacts[0].arn}/*"]
  }
}

resource "aws_iam_role_policy" "active_switch_pipeline" {
  count  = local.delivery_resources_enabled ? 1 : 0
  name   = "${local.name_prefix}-active-gala-pipeline"
  role   = aws_iam_role.active_switch_pipeline[0].id
  policy = data.aws_iam_policy_document.active_switch_pipeline[0].json
}

resource "aws_codepipeline" "active_switch" {
  count          = local.delivery_resources_enabled ? 1 : 0
  name           = "${local.name_prefix}-active-gala"
  role_arn       = aws_iam_role.active_switch_pipeline[0].arn
  pipeline_type  = "V2"
  execution_mode = "QUEUED"

  variable {
    name        = "TargetGalaSlug"
    description = "The reviewed Gala slug that will receive the single shared public EIP."
  }

  artifact_store {
    location = aws_s3_bucket.artifacts[0].bucket
    type     = "S3"
  }

  stage {
    name = "Source"
    action {
      name             = "ReviewedSwitchSource"
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
    name = "PlanSwitch"
    action {
      name             = "InspectTargetAndCurrentHolder"
      category         = "Build"
      owner            = "AWS"
      provider         = "CodeBuild"
      version          = "1"
      input_artifacts  = ["SourceOutput"]
      output_artifacts = ["SwitchPlan"]
      configuration = {
        ProjectName = aws_codebuild_project.active_switch["plan"].name
        EnvironmentVariables = jsonencode([
          { name = "TARGET_GALA_SLUG", value = "#{variables.TargetGalaSlug}", type = "PLAINTEXT" },
        ])
      }
    }
  }

  stage {
    name = "ApproveSwitch"
    action {
      name     = "ReviewExactTarget"
      category = "Approval"
      owner    = "AWS"
      provider = "Manual"
      version  = "1"
      configuration = {
        CustomData = "Review switch-plan.json: target Gala, EC2, current holder, shared EIP, and public security group."
      }
    }
  }

  stage {
    name = "ApplySwitch"
    action {
      name            = "MoveSinglePublicEip"
      category        = "Build"
      owner           = "AWS"
      provider        = "CodeBuild"
      version         = "1"
      input_artifacts = ["SourceOutput", "SwitchPlan"]
      configuration = {
        ProjectName   = aws_codebuild_project.active_switch["apply"].name
        PrimarySource = "SourceOutput"
      }
    }
  }
}
