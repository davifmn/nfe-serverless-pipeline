# terraform init -backend-config=environments/backend-prod.hcl
# The state bucket is created by infra/bootstrap.
bucket       = "REPLACE-WITH-STATE-BUCKET"
key          = "nfe-serverless-pipeline/prod.tfstate"
region       = "sa-east-1"
encrypt      = true
use_lockfile = true
# kms_key_id = "<state_kms_key_arn output of infra/bootstrap>"
