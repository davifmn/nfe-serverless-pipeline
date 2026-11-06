# Architecture and decisions

## Flow

1. A supplier, an ERP integration or an email-to-S3 robot uploads an NF-e XML to `s3://<inbox>/incoming/...xml`.
2. S3 sends an `ObjectCreated` notification to the **ingest SQS queue** (filtered on prefix `incoming/` and suffix `.xml`).
3. The **ingest Lambda** receives batches of up to 10 messages (5 s batching window, bounded concurrency). For each file it:
   - downloads the file and validates it (`src/nfe_pipeline/parser.py`);
   - **stores** valid invoices with a conditional `PutItem` (idempotent) and **publishes** `InvoiceImported` on the EventBridge bus;
   - **moves** invalid files to `rejected/` and records why, without retrying;
   - **reports** transient failures per message, so only those are retried. After 5 attempts they go to the **DLQ** and an alarm fires.
4. The **query API** (API Gateway REST → Lambda) reads DynamoDB. It needs an API key and is throttled by a usage plan.

## Why these choices

| Decision | Alternatives | Reason |
|---|---|---|
| S3 → SQS → Lambda instead of S3 → Lambda directly | Direct S3 trigger | The queue absorbs bursts (month-end uploads), gives retries with backoff and a DLQ, and lets concurrency be capped to protect downstream systems. |
| Partial batch responses | Fail the whole batch | One bad message no longer retries nine good ones. |
| Permanent vs. transient errors | Retry everything | Retrying an invalid XML can never succeed. It would only fill the DLQ and hide real incidents. |
| DynamoDB single table + GSI | RDS / Aurora | Two known access patterns (by key, by issuer and date), pay-per-request, no servers or connection pools for Lambda to exhaust. |
| Conditional writes | Read-then-write | SQS is at-least-once. The condition makes duplicates harmless with no extra read or race. |
| EventBridge bus + archive | SNS | Content-based routing for future consumers, plus replay from the archive to backfill a new one. |
| One customer managed KMS key | AWS-owned keys | Fiscal data: the key policy and CloudTrail show who can decrypt, and the key can be disabled in an incident. |
| Standard library only in the Lambda code | defusedxml, Powertools | The deployment package is just the source tree, so there is no build step and no dependency CVEs to patch in the function. XML safety comes from expat rejecting DTDs and entities. |
| arm64 (Graviton) | x86_64 | Lower price per GB-second for the same Python code. |
| Terraform modules + `terraform test` with mocked providers | Only `terraform plan` against an account | Security and wiring rules are tested on every push without credentials or cost. |
| GitHub OIDC for deploys | Access keys in secrets | No long-lived credentials. The role trusts only this repository's dev/prod environments. |

## Cost

At low volume this costs almost nothing: every compute and storage service is pay-per-request.
The fixed parts are the KMS key (about USD 1/month) and the CloudWatch alarms (about USD 0.10
per alarm per month). Check current prices on the AWS pricing pages before quoting.
