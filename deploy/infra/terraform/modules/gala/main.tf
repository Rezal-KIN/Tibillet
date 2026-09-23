locals {
  name_prefix         = "${var.project_name}-${var.gala_slug}"
  runtime_secret_name = "${var.project_name}/galas/${var.gala_slug}/runtime"
  backup_prefix       = "galas/${var.gala_slug}/"
  release_prefix      = "releases/${var.gala_slug}/"

  tags = merge({
    Project       = var.project_name
    Gala          = var.gala_slug
    Platform      = var.platform
    ManagedBy     = "terraform"
    DataIsolation = "gala-only"
  }, var.extra_tags)
}

resource "aws_secretsmanager_secret" "runtime" {
  name                    = local.runtime_secret_name
  description             = "Runtime environment for Gala ${var.gala_slug}. Secret value is injected by a human after Terraform creates this container."
  recovery_window_in_days = 7

  tags = local.tags

  lifecycle {
    prevent_destroy = true
  }
}

data "aws_iam_policy_document" "instance_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "instance" {
  name               = "${local.name_prefix}-ec2"
  assume_role_policy = data.aws_iam_policy_document.instance_assume_role.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "runtime" {
  statement {
    sid       = "ReadOnlyOwnRuntimeSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.runtime.arn]
  }

  statement {
    sid = "WriteOnlyOwnBackupPrefix"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = ["${var.backup_bucket_arn}/${local.backup_prefix}*"]
  }

  statement {
    sid       = "ListBackupBucketOnly"
    actions   = ["s3:ListBucket"]
    resources = [var.backup_bucket_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = [local.backup_prefix]
    }
  }

  dynamic "statement" {
    for_each = var.release_bucket_arn == null ? [] : [var.release_bucket_arn]

    content {
      sid       = "ReadOnlyOwnReleaseManifests"
      actions   = ["s3:GetObject"]
      resources = ["${statement.value}/${local.release_prefix}*"]
    }
  }

  dynamic "statement" {
    for_each = var.release_bucket_arn == null ? [] : [var.release_bucket_arn]

    content {
      sid       = "ListReleaseBucketOnly"
      actions   = ["s3:ListBucket"]
      resources = [statement.value]

      condition {
        test     = "StringLike"
        variable = "s3:prefix"
        values   = [local.release_prefix]
      }
    }
  }

  dynamic "statement" {
    for_each = var.ecr_lespass_repository_arn == null ? [] : [var.ecr_lespass_repository_arn]

    content {
      sid = "PullLespassReleaseImages"
      actions = [
        "ecr:BatchCheckLayerAvailability",
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer",
      ]
      resources = [statement.value]
    }
  }

  dynamic "statement" {
    for_each = var.ecr_lespass_repository_arn == null ? [] : [var.ecr_lespass_repository_arn]

    content {
      sid       = "GetEcrAuthorizationToken"
      actions   = ["ecr:GetAuthorizationToken"]
      resources = ["*"]
    }
  }
}

resource "aws_iam_role_policy" "runtime" {
  name   = "${local.name_prefix}-runtime"
  role   = aws_iam_role.instance.id
  policy = data.aws_iam_policy_document.runtime.json
}

resource "aws_iam_instance_profile" "instance" {
  name = "${local.name_prefix}-ec2"
  role = aws_iam_role.instance.name
}

resource "aws_security_group" "runtime" {
  name_prefix = "${local.name_prefix}-"
  description = "Public HTTP/HTTPS and restricted emergency SSH for Gala ${var.gala_slug}."
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTP for ACME redirect and public service"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS public service"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  dynamic "ingress" {
    for_each = toset(var.ssh_emergency_cidrs)

    content {
      description = "Emergency SSH only; SSM remains the normal operational path"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_instance" "runtime" {
  count = var.create_instance ? 1 : 0

  ami                    = var.ami_id
  instance_type          = var.instance_type
  subnet_id              = var.subnet_id
  vpc_security_group_ids = [aws_security_group.runtime.id]
  iam_instance_profile   = aws_iam_instance_profile.instance.name
  user_data = templatefile("${path.module}/bootstrap-runtime.sh.tftpl", {
    aws_region         = var.aws_region
    backup_bucket_name = var.backup_bucket_name
    domain             = var.domain
    gala_slug          = var.gala_slug
    platform           = var.platform
    repository_ref     = var.repository_ref
    repository_url     = var.repository_url
    runtime_secret_arn = aws_secretsmanager_secret.runtime.arn
  })
  # Cloud-init is first-boot only. Runtime upgrades are rerun through the
  # versioned SSM installer, never by replacing an already managed EC2.
  user_data_replace_on_change = false
  associate_public_ip_address = var.associate_public_ip_address
  monitoring                  = false
  disable_api_termination     = var.protect_from_destruction

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    encrypted             = true
    volume_type           = "gp3"
    volume_size           = var.root_volume_size_gib
    delete_on_termination = false
    tags                  = local.tags
  }

  tags = merge(local.tags, {
    Name             = local.name_prefix
    LifecycleState   = "preparation"
    DeploymentLocked = "false"
  })

  lifecycle {
    # Existing hosts are upgraded through the idempotent SSM installer. Do not
    # turn a bootstrap-template revision into an EC2 replacement or a surprise
    # user-data mutation on a live Gala.
    ignore_changes = [user_data]

    precondition {
      condition     = var.ami_id != "" && var.subnet_id != "" && var.vpc_id != ""
      error_message = "ami_id, subnet_id, and vpc_id must be explicit before creating a Gala EC2 instance."
    }

    precondition {
      condition     = var.root_volume_size_gib >= 40
      error_message = "A live Gala instance requires at least 40 GiB until measured image optimization proves a smaller size safe."
    }

    prevent_destroy = true
  }
}

resource "aws_eip" "runtime" {
  count = var.create_instance ? 1 : 0

  domain   = "vpc"
  instance = aws_instance.runtime[0].id
  tags     = local.tags

  lifecycle {
    prevent_destroy = true
  }
}
