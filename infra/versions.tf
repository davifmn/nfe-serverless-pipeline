terraform {
  # 1.10+: S3 backend locking without a DynamoDB table (use_lockfile).
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }

  # Partial configuration: bucket and key come from environments/backend-<env>.hcl.
  backend "s3" {}
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "nfe-serverless-pipeline"
      Environment = var.environment
      ManagedBy   = "terraform"
      Repository  = "github.com/davifmn/nfe-serverless-pipeline"
    }
  }
}
