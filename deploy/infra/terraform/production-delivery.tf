# A production pipeline is intentionally created per live gala. Its CodeBuild
# role can address one SSM document and one EC2 instance only; the operator
# selects a release manifest, never an EC2 target.

resource "aws_ssm_document" "production_deploy" {
  for_each        = local.production_target_galas
  name            = "${local.name_prefix}-production-${each.key}-deploy"
  document_type   = "Command"
  document_format = "JSON"

  content = jsonencode({
    schemaVersion = "2.2"
    description   = "Deploy one approved immutable TiBillet Gala release to the ${each.key} EC2 instance only."
    parameters = {
      ReleaseManifestUri = {
        type           = "String"
        description    = "S3 URI of the immutable release manifest under this Gala's release prefix."
        allowedPattern = "^s3://${aws_s3_bucket.backups[0].bucket}/releases/${each.key}/[A-Za-z0-9._-]+\\.json$"
      }
    }
    mainSteps = [{
      action = "aws:runShellScript"
      name   = "DeployApprovedRelease"
      inputs = {
        runCommand = [
          "set -eu",
          "manifest=$(mktemp)",
          "trap 'rm -f \"$manifest\"' EXIT",
          "aws s3 cp --only-show-errors '{{ ReleaseManifestUri }}' \"$manifest\" --region ${var.aws_region}",
          "commit=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[\"fork_commit\"])' \"$manifest\")",
          "case \"$commit\" in *[!0-9a-f]*|'') echo 'invalid release commit' >&2; exit 1;; esac",
          "test \"$(printf %s \"$commit\" | wc -c | tr -d ' ')\" -eq 40",
          "repo=/opt/tibillet-gala/repository",
          "git -C \"$repo\" fetch --depth 1 origin \"$commit\"",
          "git -C \"$repo\" checkout --detach FETCH_HEAD",
          "python3 \"$repo/deploy/tools/runtime/reconcile-runtime.py\" /etc/tibillet-gala/${each.key}.conf ${each.key} '${module.gala[each.key].generated_secret_arn}' '${each.key == "gala-smoke" ? aws_secretsmanager_secret.stripe_test[0].arn : aws_secretsmanager_secret.stripe_live[0].arn}' '${aws_secretsmanager_secret.shared_mail[0].arn}'",
          "bash \"$repo/deploy/tools/runtime/install-runtime-contract.sh\" /etc/tibillet-gala/${each.key}.conf",
          "/usr/local/lib/tibillet-gala/deploy-release-from-s3.sh /etc/tibillet-gala/${each.key}.conf '{{ ReleaseManifestUri }}'",
        ]
      }
    }]
  })

  lifecycle {
    precondition {
      condition     = module.gala[each.key].instance_id != null
      error_message = "A production pipeline may only be created for a Gala with an EC2 instance created by Terraform."
    }
  }
}

resource "aws_iam_role" "production_build" {
  for_each           = local.production_target_galas
  name               = "${local.name_prefix}-production-${each.key}-build"
  assume_role_policy = data.aws_iam_policy_document.codebuild_assume_role.json
}

data "aws_iam_policy_document" "production_build" {
  for_each = local.production_target_galas

  statement {
    sid       = "ReadValidatedPipelineArtifact"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${aws_s3_bucket.artifacts[0].arn}/*"]
  }

  statement {
    sid       = "WriteShortLivedBuildLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.production_deploy[each.key].arn}:*"]
  }

  statement {
    sid       = "WriteOnlyTargetGalaReleaseManifest"
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${aws_s3_bucket.backups[0].arn}/releases/${each.key}/*"]
  }

  statement {
    sid     = "DeployOnlyToTheTargetGala"
    actions = ["ssm:SendCommand"]
    resources = [
      aws_ssm_document.production_deploy[each.key].arn,
      "arn:${data.aws_partition.current.partition}:ec2:${var.aws_region}:${data.aws_caller_identity.current.account_id}:instance/${module.gala[each.key].instance_id}",
    ]
  }

  statement {
    sid       = "ReadOwnDeploymentCommandStatus"
    actions   = ["ssm:GetCommandInvocation"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "production_build" {
  for_each = local.production_target_galas
  name     = "${local.name_prefix}-production-${each.key}-build"
  role     = aws_iam_role.production_build[each.key].id
  policy   = data.aws_iam_policy_document.production_build[each.key].json
}

resource "aws_codebuild_project" "production" {
  for_each       = local.production_target_galas
  name           = "${local.name_prefix}-production-${each.key}"
  description    = "Manually promotes one reviewed immutable release for ${each.key}; it cannot target another Gala."
  service_role   = aws_iam_role.production_build[each.key].arn
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
      value = each.key
    }
    environment_variable {
      name  = "RELEASE_BUCKET"
      value = aws_s3_bucket.backups[0].bucket
    }
    environment_variable {
      name  = "TARGET_INSTANCE_ID"
      value = module.gala[each.key].instance_id
    }
    environment_variable {
      name  = "DEPLOYMENT_DOCUMENT_NAME"
      value = aws_ssm_document.production_deploy[each.key].name
    }
  }

  logs_config {
    cloudwatch_logs {
      group_name  = aws_cloudwatch_log_group.production_deploy[each.key].name
      stream_name = "deploy"
    }
  }

  source {
    type      = "CODEPIPELINE"
    buildspec = file("${path.root}/../../buildspec/tibillet-production.yml")
  }
}

resource "aws_iam_role" "production_pipeline" {
  for_each = local.production_target_galas
  name     = "${local.name_prefix}-production-${each.key}-pipeline"
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
  for_each = local.production_target_galas

  statement {
    sid       = "UseOnlyGalaGitHubConnection"
    actions   = ["codeconnections:UseConnection", "codestar-connections:UseConnection"]
    resources = [var.github_connection_arn]
  }

  statement {
    sid       = "RunOnlyThisGalaProductionBuild"
    actions   = ["codebuild:StartBuild", "codebuild:BatchGetBuilds"]
    resources = [aws_codebuild_project.production_validate[each.key].arn, aws_codebuild_project.production[each.key].arn]
  }

  statement {
    sid       = "UseShortLivedArtifacts"
    actions   = ["s3:GetBucketVersioning", "s3:GetObject", "s3:GetObjectVersion", "s3:PutObject"]
    resources = [aws_s3_bucket.artifacts[0].arn, "${aws_s3_bucket.artifacts[0].arn}/*"]
  }
}

resource "aws_iam_role_policy" "production_pipeline" {
  for_each = local.production_target_galas
  name     = "${local.name_prefix}-production-${each.key}-pipeline"
  role     = aws_iam_role.production_pipeline[each.key].id
  policy   = data.aws_iam_policy_document.production_pipeline[each.key].json
}

resource "aws_codepipeline" "production" {
  for_each      = local.production_target_galas
  name          = "${local.name_prefix}-production-${each.key}"
  role_arn      = aws_iam_role.production_pipeline[each.key].arn
  pipeline_type = "V2"

  variable {
    name          = "ReleaseManifestPath"
    default_value = "releases/${each.key}/production.json"
    description   = "Repo-relative immutable release manifest for ${each.key}. Its gala_slug must match this pipeline."
  }

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
        ConnectionArn        = var.github_connection_arn
        FullRepositoryId     = "${var.github_owner}/${var.github_repository}"
        BranchName           = var.production_source_branch
        DetectChanges        = "false"
        OutputArtifactFormat = "CODEBUILD_CLONE_REF"
      }
    }
  }

  stage {
    name = "ValidatePromotion"

    action {
      name             = "ProveTestedImages"
      category         = "Build"
      owner            = "AWS"
      provider         = "CodeBuild"
      version          = "1"
      namespace        = "ValidatedRelease"
      input_artifacts  = ["SourceOutput"]
      output_artifacts = ["ValidatedOutput"]

      configuration = {
        ProjectName = aws_codebuild_project.production_validate[each.key].name
        EnvironmentVariables = jsonencode([
          {
            name  = "RELEASE_MANIFEST_PATH"
            value = "#{variables.ReleaseManifestPath}"
            type  = "PLAINTEXT"
          },
        ])
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
      configuration = {
        CustomData = "Validation automatique réussie. Artefact exact : #{ValidatedRelease.APPROVAL_SUMMARY}"
      }
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
      input_artifacts = ["ValidatedOutput"]

      configuration = {
        ProjectName = aws_codebuild_project.production[each.key].name
        EnvironmentVariables = jsonencode([
          {
            name  = "APPROVED_MANIFEST_SHA256"
            value = "#{ValidatedRelease.MANIFEST_SHA256}"
            type  = "PLAINTEXT"
          },
        ])
      }
    }
  }
}
