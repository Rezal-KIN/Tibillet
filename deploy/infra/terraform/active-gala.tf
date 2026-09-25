# The existing Aix EIP becomes the one account-level public address. Its
# association is changed only by the explicit active-Gala switch workflow.
moved {
  from = module.gala["gala-am-aix"].aws_eip.runtime[0]
  to   = aws_eip.shared_public[0]
}

resource "aws_eip" "shared_public" {
  count  = local.gala_resources_enabled ? 1 : 0
  domain = "vpc"
  tags = merge(local.common_tags, {
    Name = "${var.project_name}-shared-public"
  })

  lifecycle {
    prevent_destroy = true
    # The explicit switch workflow moves this EIP between approved instances.
    ignore_changes = [instance]
  }
}

# All Galas keep their own outbound security group. Public ingress is granted
# only by attaching this additional group to the active Gala's primary ENI.
resource "aws_security_group" "active_public" {
  count       = local.gala_resources_enabled ? 1 : 0
  name_prefix = "${local.name_prefix}-active-public-"
  description = "HTTP and HTTPS ingress for the one active Gala instance."
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTP for ACME and redirect"
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

  tags = local.common_tags

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_ssm_parameter" "active_gala" {
  count      = local.gala_resources_enabled ? 1 : 0
  depends_on = [aws_iam_role_policy.foundation_build]
  name       = "/${var.project_name}/active-gala"
  type       = "String"
  value      = "none"
  tags       = local.common_tags

  lifecycle {
    prevent_destroy = true
    # Only a completed public-IP switch updates the active Gala marker.
    ignore_changes = [value]
  }
}
