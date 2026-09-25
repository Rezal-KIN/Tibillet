locals {
  name_prefix    = "${var.project_name}-${var.gala_slug}"
  backup_prefix  = "galas/${var.gala_slug}/"
  release_prefix = "releases/${var.gala_slug}/"

  tags = merge({
    Project       = var.project_name
    Gala          = var.gala_slug
    Platform      = var.platform
    ManagedBy     = "terraform"
    DataIsolation = "gala-only"
  }, var.extra_tags)
}

resource "aws_secretsmanager_secret" "generated" {
  name                    = "${var.project_name}/galas/${var.gala_slug}/generated"
  description             = "Stable application keys and database passwords, initialized once by the Foundation pipeline."
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
    sid       = "ReadOnlyOwnRuntimeSecrets"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = compact([aws_secretsmanager_secret.generated.arn, var.shared_stripe_secret_arn, var.shared_mail_secret_arn])
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
  # Keep the existing description to avoid replacing a security group still
  # attached to its EC2. The ingress rules are removed in place.
  description = "Public HTTP/HTTPS and restricted emergency SSH for Gala ${var.gala_slug}."
  vpc_id      = var.vpc_id

  ingress = [
    for cidr in var.ssh_emergency_cidrs : {
      description      = "Emergency SSH only; SSM remains the normal operational path"
      from_port        = 22
      to_port          = 22
      protocol         = "tcp"
      cidr_blocks      = [cidr]
      ipv6_cidr_blocks = []
      prefix_list_ids  = []
      security_groups  = []
      self             = false
    }
  ]

  dynamic "egress" {
    for_each = var.gala_slug == "gala-smoke" ? [
      { port = 53, protocol = "tcp" },
      { port = 53, protocol = "udp" },
      { port = 80, protocol = "tcp" },
      { port = 443, protocol = "tcp" },
    ] : [{ port = 0, protocol = "-1" }]
    content {
      from_port   = egress.value.port
      to_port     = egress.value.port
      protocol    = egress.value.protocol
      cidr_blocks = ["0.0.0.0/0"]
    }
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
    aws_region               = var.aws_region
    backup_bucket_name       = var.backup_bucket_name
    domain                   = var.domain
    gala_slug                = var.gala_slug
    platform                 = var.platform
    repository_ref           = var.repository_ref
    repository_url           = var.repository_url
    generated_secret_arn     = aws_secretsmanager_secret.generated.arn
    shared_stripe_secret_arn = var.shared_stripe_secret_arn
    shared_mail_secret_arn   = var.shared_mail_secret_arn
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
    ignore_changes = [user_data, vpc_security_group_ids, associate_public_ip_address]

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
