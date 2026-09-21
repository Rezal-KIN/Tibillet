resource "aws_s3_bucket" "backups" {
  count  = var.enable_additive_resources && var.enable_backup_storage ? 1 : 0
  bucket = local.backup_bucket_name

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "backups" {
  count                   = var.enable_additive_resources && var.enable_backup_storage ? 1 : 0
  bucket                  = aws_s3_bucket.backups[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "backups" {
  count  = var.enable_additive_resources && var.enable_backup_storage ? 1 : 0
  bucket = aws_s3_bucket.backups[0].id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "backups" {
  count  = var.enable_additive_resources && var.enable_backup_storage ? 1 : 0
  bucket = aws_s3_bucket.backups[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "backups" {
  count  = var.enable_additive_resources && var.enable_backup_storage ? 1 : 0
  bucket = aws_s3_bucket.backups[0].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "backups" {
  count  = var.enable_additive_resources && var.enable_backup_storage ? 1 : 0
  bucket = aws_s3_bucket.backups[0].id

  rule {
    id     = "expire-noncurrent-backups"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = var.backup_retention_days
    }
  }
}

resource "aws_s3_bucket" "artifacts" {
  count  = var.enable_additive_resources && var.enable_delivery_platform ? 1 : 0
  bucket = "${local.name_prefix}-${data.aws_caller_identity.current.account_id}-artifacts"
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  count                   = local.delivery_resources_enabled ? 1 : 0
  bucket                  = aws_s3_bucket.artifacts[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "artifacts" {
  count  = var.enable_additive_resources && var.enable_delivery_platform ? 1 : 0
  bucket = aws_s3_bucket.artifacts[0].id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  count  = var.enable_additive_resources && var.enable_delivery_platform ? 1 : 0
  bucket = aws_s3_bucket.artifacts[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "artifacts" {
  count  = var.enable_additive_resources && var.enable_delivery_platform ? 1 : 0
  bucket = aws_s3_bucket.artifacts[0].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  count  = var.enable_additive_resources && var.enable_delivery_platform ? 1 : 0
  bucket = aws_s3_bucket.artifacts[0].id

  rule {
    id     = "expire-delivery-artifacts"
    status = "Enabled"

    filter {}

    expiration {
      days = 7
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }
}
