terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state in the bucket created once by infra/terraform-bootstrap. Native
  # S3 locking (use_lockfile), no DynamoDB table. Bucket/key/region come from a
  # private backend.hcl outside Git; see examples/backend.hcl.example.
  backend "s3" {
    use_lockfile = true
    encrypt      = true
  }
}
