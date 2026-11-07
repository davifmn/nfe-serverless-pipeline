# One-time setup per AWS account, applied by a person with admin rights:
#   terraform init && terraform apply -var github_repository=davifmn/nfe-serverless-pipeline
# Creates the remote-state bucket and lets GitHub Actions deploy through OIDC, so no
# long-lived AWS keys are stored in GitHub.

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.region
}

variable "region" {
  type    = string
  default = "sa-east-1"
}

variable "github_repository" {
  description = "owner/repo allowed to assume the deploy role."
  type        = string
  default     = "davifmn/nfe-serverless-pipeline"
}

variable "environments" {
  description = "GitHub environments allowed to deploy (protect prod with required reviewers)."
  type        = list(string)
  default     = ["dev", "prod"]
}

data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
}

# --- Terraform state ---------------------------------------------------------------------

resource "aws_s3_bucket" "state" {
  bucket_prefix = "nfe-terraform-state-"
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled" # lets you recover a previous state file
  }
}

# State files can contain secrets and resource details, so they get their own key.
resource "aws_kms_key" "state" {
  description             = "Terraform state of nfe-serverless-pipeline"
  enable_key_rotation     = true
  deletion_window_in_days = 30
}

resource "aws_kms_alias" "state" {
  name          = "alias/nfe-terraform-state"
  target_key_id = aws_kms_key.state.key_id
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.state.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.state]
}

# --- GitHub Actions OIDC -----------------------------------------------------------------

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

resource "aws_iam_role" "deploy" {
  name = "nfe-github-deploy"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = { "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com" }
        # Only workflow jobs of this repository running in one of the listed environments.
        StringLike = {
          "token.actions.githubusercontent.com:sub" = [
            for env in var.environments : "repo:${var.github_repository}:environment:${env}"
          ]
        }
      }
    }]
  })
}

# Deploys need to manage many service types, so PowerUserAccess covers them. IAM is
# excluded from it; a separate policy allows IAM changes only on this project's roles.
resource "aws_iam_role_policy_attachment" "power_user" {
  role       = aws_iam_role.deploy.name
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"
}

resource "aws_iam_role_policy" "project_roles" {
  name = "manage-project-roles"
  role = aws_iam_role.deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "ProjectRolesOnly"
      Effect = "Allow"
      Action = [
        "iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:UpdateRole", "iam:TagRole", "iam:UntagRole",
        "iam:PutRolePolicy", "iam:GetRolePolicy", "iam:DeleteRolePolicy", "iam:ListRolePolicies",
        "iam:ListAttachedRolePolicies", "iam:ListInstanceProfilesForRole", "iam:PassRole",
      ]
      Resource = "arn:aws:iam::${local.account_id}:role/nfe-*"
    }]
  })
}

output "state_bucket" {
  value = aws_s3_bucket.state.bucket
}

output "state_kms_key_arn" {
  description = "Set as kms_key_id in environments/backend-<env>.hcl."
  value       = aws_kms_key.state.arn
}

output "deploy_role_arn" {
  description = "Set as the AWS_DEPLOY_ROLE_ARN variable of the GitHub environments."
  value       = aws_iam_role.deploy.arn
}
