output "state_bucket_name" {
  value       = aws_s3_bucket.tfstate.bucket
  description = "Copy this into infra/terraform/backend.hcl (bucket = ...). See infra/terraform/examples/backend.hcl.example."
}
