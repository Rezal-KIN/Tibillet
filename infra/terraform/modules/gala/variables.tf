variable "project_name" { type = string }
variable "aws_region" { type = string }
variable "gala_slug" { type = string }
variable "platform" { type = string }
variable "domain" { type = string }
variable "vpc_id" { type = string }
variable "subnet_id" { type = string }
variable "ami_id" { type = string }
variable "instance_type" { type = string }
variable "root_volume_size_gib" { type = number }
variable "backup_bucket_arn" { type = string }
variable "backup_bucket_name" { type = string }
variable "release_bucket_arn" {
  type    = string
  default = null
}
variable "release_bucket_name" {
  type    = string
  default = null
}
variable "ssh_emergency_cidrs" { type = list(string) }
variable "create_instance" { type = bool }
variable "protect_from_destruction" { type = bool }
variable "extra_tags" { type = map(string) }
