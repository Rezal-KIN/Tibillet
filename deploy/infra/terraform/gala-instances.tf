module "gala" {
  source   = "./modules/gala"
  for_each = var.enable_additive_resources && var.enable_backup_storage ? var.galas : {}

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
  repository_url              = "https://github.com/${var.github_owner}/${var.github_repository}.git"
  repository_ref              = var.runtime_repository_ref
  ssh_emergency_cidrs         = each.value.ssh_emergency_cidrs
  associate_public_ip_address = each.value.associate_public_ip_address
  create_instance             = each.value.create_instance
  protect_from_destruction    = each.value.protect_from_destruction
  extra_tags                  = var.extra_tags
}
