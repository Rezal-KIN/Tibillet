module "gala" {
  source   = "./modules/gala"
  for_each = var.enable_additive_resources && var.enable_backup_storage ? var.galas : {}
  # The existing Foundation pipeline updates its own CodeBuild role during
  # the first maintenance run. Do that before creating generated secrets.
  depends_on = [aws_iam_role_policy.foundation_build]

  project_name         = var.project_name
  aws_region           = var.aws_region
  gala_slug            = each.key
  platform             = each.value.platform
  domain               = each.value.domain
  vpc_id               = var.vpc_id
  subnet_id            = var.subnet_id
  ami_id               = var.ec2_ami_id
  instance_type        = each.value.instance_type
  root_volume_size_gib = each.value.root_volume_size_gib
  backup_bucket_arn    = aws_s3_bucket.backups[0].arn
  backup_bucket_name   = aws_s3_bucket.backups[0].bucket
  # Release manifests must outlive the seven-day CodePipeline artifact bucket.
  # The backup bucket has versioning and no current-version expiry; each EC2
  # can still read only its own releases/<slug>/ prefix.
  release_bucket_arn          = local.delivery_resources_enabled ? aws_s3_bucket.backups[0].arn : null
  release_bucket_name         = local.delivery_resources_enabled ? aws_s3_bucket.backups[0].bucket : null
  ecr_lespass_repository_arn  = local.delivery_resources_enabled ? aws_ecr_repository.lespass[0].arn : null
  shared_stripe_secret_arn    = each.key == "gala-smoke" ? aws_secretsmanager_secret.stripe_test[0].arn : aws_secretsmanager_secret.stripe_live[0].arn
  shared_mail_secret_arn      = aws_secretsmanager_secret.shared_mail[0].arn
  repository_url              = "https://github.com/${var.github_owner}/${var.github_repository}.git"
  repository_ref              = var.runtime_repository_ref
  ssh_emergency_cidrs         = each.value.ssh_emergency_cidrs
  associate_public_ip_address = each.value.associate_public_ip_address
  create_instance             = each.value.create_instance
  protect_from_destruction    = each.value.protect_from_destruction
  extra_tags                  = var.extra_tags
}

# Move only the two disposable trial hosts to a resource without the
# production prevent_destroy rule. Aix and Smoke keep that rule unchanged.
moved {
  from = module.gala["gala-validation"].aws_instance.runtime[0]
  to   = module.gala["gala-validation"].aws_instance.retirable[0]
}

moved {
  from = module.gala["gala-validation-2"].aws_instance.runtime[0]
  to   = module.gala["gala-validation-2"].aws_instance.retirable[0]
}

# The temporary Gala was created by Foundation solely to verify a fresh
# production chain. Its retirement is separately gated; Aix and Smoke stay put.
moved {
  from = module.gala["gala-verification"].aws_instance.runtime[0]
  to   = module.gala["gala-verification"].aws_instance.retirable[0]
}

# Exact disposable host created for the automatic first-execution test.
moved {
  from = module.gala["gala-first-run-20260926"].aws_instance.runtime[0]
  to   = module.gala["gala-first-run-20260926"].aws_instance.retirable[0]
}
