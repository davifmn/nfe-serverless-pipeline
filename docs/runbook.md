# Runbook

## DLQ not empty
**Alarm:** `<name>-dlq-not-empty`. Messages failed every delivery attempt (5) and moved to the
dead-letter queue. Invalid documents never land here, because they are rejected and acknowledged.
What does land here is a transient error that kept happening (throttling, a missing KMS
permission, an EventBridge outage).

1. Find the cause in the ingest logs (CloudWatch Logs Insights, log group `/aws/lambda/<name>-ingest`):
   ```
   fields @timestamp, message_id, error
   | filter event = "message_failed"
   | sort @timestamp desc
   ```
2. Fix it (deploy, permission, quota).
3. Send the messages back to the main queue. Processing is idempotent, so this is safe:
   `aws sqs start-message-move-task --source-arn <dlq-arn>`

## Ingest backlog
**Alarm:** `<name>-ingest-backlog`. The oldest message has waited more than 15 minutes.

- Look for a burst of uploads in the `NumberOfMessagesReceived` metric.
- If the ingest function is at `maximum_concurrency`, raise `ingest_max_concurrency` (watch DynamoDB and downstream consumers).
- If invocations are failing, check the function's error alarm and the logs.

## Lambda errors or throttles
**Alarms:** `<name>-ingest-errors`, `<name>-api-errors`, `*-throttles`.

- Errors in ingest are retried per message. Check whether they are reaching the DLQ.
- Throttles: the account concurrency limit, or reserved concurrency, is too low.

## API 5xx
**Alarm:** `<name>-api-5xx`. Check the `/aws/lambda/<name>-api` logs and the access log
(`/aws/apigateway/<name>-api/access`). Note that 4xx responses (bad CNPJ, missing key) are client errors and don't alarm.

## A supplier says an invoice "disappeared"
1. Was it rejected? Look for `PK = REJECTED#incoming/<path>` in DynamoDB, or for the file under `rejected/` in the bucket. The record has the `error_code` (for example `invalid_access_key`, `total_mismatch`).
2. Was it uploaded outside `incoming/`, or without the `.xml` suffix? Only those trigger ingestion.
3. To reprocess after a fix, copy the file back to `incoming/`. A duplicate is a no-op.
