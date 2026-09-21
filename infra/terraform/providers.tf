provider "aws" {
  region = var.aws_region

  default_tags {
    tags = merge(local.common_tags, var.extra_tags)
  }
}

# IAM Identity Center API calls must use the region where the independent Gala
# Identity Center is enabled. This is deliberately separate from runtime EC2.
provider "aws" {
  alias  = "identity_center"
  region = var.identity_center_region

  default_tags {
    tags = merge(local.common_tags, var.extra_tags)
  }
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

data "aws_instance" "bapts" {
  instance_id = var.bapts_instance_id
}

check "gala_account_allowlist" {
  assert {
    condition     = data.aws_caller_identity.current.account_id == var.gala_account_id
    error_message = "Terraform is connected to an account outside the Gala allowlist. Verify aws sts get-caller-identity before continuing."
  }
}

check "bapts_runtime_allowlist" {
  assert {
    condition     = data.aws_instance.bapts.tags["Name"] == var.bapts_instance_name
    error_message = "The allowlisted Bapts instance ID does not have the expected Name tag. Refusing to continue."
  }
}
