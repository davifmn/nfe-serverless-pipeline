# terraform init -backend-config=environments/backend-dev.hcl
# The state bucket is created by infra/bootstrap.
bucket       = "REPLACE-WITH-STATE-BUCKET"
key          = "nfe-serverless-pipeline/dev.tfstate"
region       = "sa-east-1"
encrypt      = true
use_lockfile = true
