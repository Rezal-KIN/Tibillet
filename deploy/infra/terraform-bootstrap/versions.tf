terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Deliberately local state. This config creates the bucket that every other
  # Terraform state (infra/terraform) lives in, so it cannot depend on that
  # bucket existing yet. Applied once, by a human, from infra/terraform-bootstrap/.
}
