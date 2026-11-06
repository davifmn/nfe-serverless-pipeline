# nfe-serverless-pipeline

[![CI](https://github.com/davifmn/nfe-serverless-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/davifmn/nfe-serverless-pipeline/actions/workflows/ci.yml)

Event-driven ingestion of Brazilian electronic invoices (NF-e) on AWS, built entirely with
Terraform: **S3 → SQS → Lambda → DynamoDB**, domain events on **EventBridge**, a query API on
**API Gateway**, alarms and a dashboard in **CloudWatch**, all encrypted with a customer managed
**KMS** key. Deploys come from GitHub Actions via **OIDC**, with no stored AWS keys.

```
 supplier / ERP                                                    other teams
      │ PUT incoming/*.xml                                            ▲  InvoiceImported
      ▼                                                               │
 ┌──────────┐ ObjectCreated  ┌──────────────┐ batches ┌──────────────┴─┐ PutItem  ┌───────────────┐
 │ S3 inbox │ ─────────────▶ │ SQS ingest   │ ──────▶ │ Lambda ingest  │ ───────▶ │ DynamoDB      │
 │ (KMS,    │                │ (KMS, 6x vis)│         │ validate, dedupe│ (if new) │ single table  │
 │ versioned│ ◀── rejected/ ─│      │ 5 fails        │ partial retries │          │ + GSI1        │
 │ lifecycle│                │      ▼                └────────────────┘          └──────┬────────┘
 └──────────┘                │ SQS DLQ ── alarm ──▶ SNS                                 │ Get/Query
                             └──────────────┘                ┌────────────┐  ┌──────────┴───────┐
                                                clients ───▶ │ API GW REST│─▶│ Lambda api       │
                                              (x-api-key)    │ usage plan │  │ (read-only role) │
                                                             └────────────┘  └──────────────────┘
```

**[docs/architecture.md](docs/architecture.md)** explains each choice and its alternatives.
**[docs/runbook.md](docs/runbook.md)** says what to do when each alarm fires.

## What it does

- **Validates every invoice** before storing it: XML safety (DTD/entity rejection), access-key
  check digit, every field encoded in the key against the body, CNPJ/CPF check digits (including
  the alphanumeric CNPJ issued since July 2026), and items adding up to the declared total.
- **Handles failures by type:**
  - an invalid file is moved to `rejected/`, recorded and *not* retried;
  - a transient AWS error retries *only that message* (SQS partial batch response);
  - a message that fails 5 times goes to the DLQ and raises an alarm.
- **Is idempotent:** SQS delivers at least once and suppliers re-upload. A conditional `PutItem` makes both harmless.
- **Publishes `InvoiceImported`** on an EventBridge bus with a 30-day replay archive, for downstream consumers.
- **Serves a query API:**
  - `GET /invoices/{access_key}`;
  - `GET /issuers/{cnpj}/invoices?from=&to=&limit=&cursor=` (newest first, cursor pagination);
  - each client has its own API key with rate limit and monthly quota; `/health` is open.
- **Keeps invoices for the legal period:** XML moves to Glacier Instant Retrieval after 90 days and expires after 6 years. The module refuses a retention under 5 years.

## Repository layout

| Path | Contents |
|---|---|
| `src/nfe_pipeline/` | Lambda code (standard library + boto3 only): parser, check digits, DynamoDB repository, events, `handlers/ingest.py`, `handlers/api.py` |
| `tests/` | 24 pytest tests with **moto**, including the real S3 → SQS notification flow |
| `infra/` | Root module composing the stack, plus `environments/{dev,prod}.tfvars` and the S3 backend configs |
| `infra/modules/lambda_function` | Reusable function: zip, least-privilege role, encrypted log group, X-Ray, error/throttle alarms |
| `infra/modules/ingestion` | Bucket (private, KMS, versioning, lifecycle, TLS-only), queue + DLQ, DynamoDB, EventBridge |
| `infra/modules/api` | REST API, API keys, usage plan, stage with access logs and X-Ray |
| `infra/modules/monitoring` | SNS topic, DLQ/backlog/5xx alarms, dashboard |
| `infra/bootstrap` | One-time account setup: remote state bucket, GitHub OIDC provider, deploy role |
| `infra/tests` | `terraform test` suites against a mocked AWS provider |

## Tested without an AWS account

| Layer | How |
|---|---|
| Application | `pytest` with moto: S3, SQS, DynamoDB and EventBridge in memory |
| Infrastructure rules | `terraform test` with `mock_provider "aws"`: no wildcard IAM actions, a read-only API role, ingest limited to `incoming/`, DLQ after 5 receives, visibility = 6× timeout, TLS-only private bucket, KMS everywhere, legal retention, API keys on data routes, GET-only invoke permission, OIDC trust limited to this repo's environments |
| Style and security | `terraform fmt`, `terraform validate`, `tflint` (AWS ruleset), Trivy misconfiguration scan (fails on HIGH/CRITICAL) |

```sh
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]" && .venv/bin/pytest
cd infra && terraform init -backend=false && terraform test
```

## Deploying to a real account

1. Once per account, as an administrator: `cd infra/bootstrap && terraform init && terraform apply`.
   This prints the state bucket and the deploy role ARN.
2. In GitHub, create the environments `dev` and `prod` (with required reviewers on `prod`) and set
   the variables `AWS_DEPLOY_ROLE_ARN` and `TF_STATE_BUCKET`.
3. Run the **Deploy** workflow (Actions → Deploy), first with `apply` off to review the plan.
   After applying, it uploads a synthetic invoice and waits for it to appear in the API.

Manually: `terraform -chdir=infra init -backend-config=environments/backend-dev.hcl -backend-config=bucket=<state bucket>`,
then `terraform -chdir=infra apply -var-file=environments/dev.tfvars`.

Try it after deploying:

```sh
aws s3 cp nota.xml s3://$(terraform -chdir=infra output -raw inbox_bucket)/incoming/
KEY=$(aws apigateway get-api-key --api-key <id from api_key_ids> --include-value --query value --output text)
curl -H "x-api-key: $KEY" "$(terraform -chdir=infra output -raw api_url)/invoices/<access key>"
```

## Related

The validation rules come from my [nfe-importer](https://github.com/davifmn/nfe-importer), a
Django/MySQL version of the same problem. This repository is the serverless, event-driven take.

## License

MIT. Sample invoices in the tests are fictitious.
