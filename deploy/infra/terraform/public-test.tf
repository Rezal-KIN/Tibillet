# The test host has its own public address. The active-Gala workflow continues
# to own only the production EIP; a test switch must never steal that address.
variable "enable_public_cawl_test" {
  description = "Enable the independent public CAWL test endpoint after production activation."
  type        = bool
  default     = false

  validation {
    condition = !var.enable_public_cawl_test || (
      var.enable_cawl_platform && var.reserve_cawl_test_address &&
      try(var.galas["gala-smoke-cawl"].domain == "gala-test.rezal.fr" && var.galas["gala-smoke-cawl"].payment_provider == "cawl", false)
    )
    error_message = "Public CAWL test requires the CAWL platform and the exact approved test domain."
  }
}

variable "reserve_cawl_test_address" {
  description = "Reserve the independent test address without changing routing or application data."
  type        = bool
  default     = false
  validation {
    condition     = !var.reserve_cawl_test_address || (var.enable_cawl_platform && try(var.galas["gala-smoke-cawl"].create_instance && var.galas["gala-smoke-cawl"].payment_provider == "cawl", false))
    error_message = "A reserved test address requires the existing CAWL Smoke host."
  }
}

resource "aws_eip" "cawl_test_public" {
  count  = var.reserve_cawl_test_address ? 1 : 0
  domain = "vpc"
  tags = merge(local.common_tags, {
    Name               = "${var.project_name}-cawl-test-public"
    RuntimeEnvironment = "test"
  })

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_eip_association" "cawl_test_public" {
  count               = var.enable_public_cawl_test ? 1 : 0
  allocation_id       = aws_eip.cawl_test_public[0].id
  instance_id         = module.gala[local.cawl_smoke_slug].instance_id
  allow_reassociation = false

  lifecycle {
    prevent_destroy = true
    precondition {
      condition = (
        aws_ssm_parameter.active_gala[0].value != local.cawl_smoke_slug &&
        aws_eip.shared_public[0].instance != module.gala[local.cawl_smoke_slug].instance_id
      )
      error_message = "Activate and verify production first; the test host must no longer hold the production EIP."
    }
  }
}

output "cawl_test_public_ip" {
  value       = var.reserve_cawl_test_address ? aws_eip.cawl_test_public[0].public_ip : null
  description = "Independent CAWL test IPv4; never used by the active production switch."
}
