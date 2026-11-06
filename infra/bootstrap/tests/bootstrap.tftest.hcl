mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
    }
  }
  mock_resource "aws_iam_openid_connect_provider" {
    defaults = {
      arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
    }
  }
}

run "deploy_role_trusts_only_this_repository_and_its_environments" {
  command = apply

  assert {
    condition = jsondecode(aws_iam_role.deploy.assume_role_policy).Statement[0].Condition.StringLike["token.actions.githubusercontent.com:sub"] == [
      "repo:davifmn/nfe-serverless-pipeline:environment:dev",
      "repo:davifmn/nfe-serverless-pipeline:environment:prod",
    ]
    error_message = "The deploy role must not be assumable from other repositories or from branches without an environment."
  }

  assert {
    condition     = jsondecode(aws_iam_role.deploy.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"
    error_message = "The token audience must be STS."
  }

  assert {
    condition     = jsondecode(aws_iam_role_policy.project_roles.policy).Statement[0].Resource == "arn:aws:iam::123456789012:role/nfe-*"
    error_message = "IAM changes are limited to this project's roles."
  }

  assert {
    condition     = one(aws_s3_bucket_versioning.state.versioning_configuration).status == "Enabled"
    error_message = "State must be versioned."
  }
}
