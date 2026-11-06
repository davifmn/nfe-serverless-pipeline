"""Ingest Lambda: SQS batch of S3 notifications → validated invoices in DynamoDB.

Failure handling follows the kind of error:

* **Invalid document** (bad XML, wrong check digit, totals don't add up): permanent.
  The file is moved to ``rejected/``, a rejection record is written and the message is
  acknowledged. Retrying would fail the same way.
* **Transient AWS error** (throttling, timeouts, 5xx): the message is reported in
  ``batchItemFailures`` so only *that* message is retried. After ``maxReceiveCount``
  attempts SQS moves it to the dead-letter queue, which raises an alarm.
* **Duplicate delivery or re-upload**: the conditional write makes it a no-op.

Events on EventBridge are at-least-once: they are published again for duplicates, so a
failure between "stored" and "event sent" is repaired by the retry. Consumers dedupe on
``access_key``.
"""

from __future__ import annotations

import json
import logging
from urllib.parse import unquote_plus

from botocore.exceptions import ClientError

from .. import events
from ..config import clients, settings
from ..logs import log
from ..parser import NFeError, parse_nfe
from ..repository import InvoiceRepository


def handler(event: dict, context) -> dict:
    failures = []
    for record in event.get("Records", []):
        try:
            process_message(record)
        except Exception as exc:  # noqa: BLE001 - any unexpected error: retry this message only
            log(
                "message_failed", logging.ERROR, message_id=record.get("messageId"), error=repr(exc)
            )
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}


def process_message(record: dict) -> None:
    try:
        body = json.loads(record["body"])
    except (KeyError, ValueError):
        log("malformed_message_dropped", logging.WARNING, message_id=record.get("messageId"))
        return
    if body.get("Event") == "s3:TestEvent":  # sent once when the notification is configured
        return
    for s3_record in body.get("Records", []):
        obj = s3_record["s3"]["object"]
        process_object(
            bucket=s3_record["s3"]["bucket"]["name"],
            key=unquote_plus(obj["key"]),  # S3 event keys are URL-encoded
            size=int(obj.get("size", 0)),
        )


def process_object(*, bucket: str, key: str, size: int) -> str:
    cfg, aws = settings(), clients()
    repo = InvoiceRepository(aws["table"])

    if size > cfg.max_object_bytes:
        return _reject(bucket, key, "too_large", f"{size} bytes", repo)
    try:
        body = aws["s3"].get_object(Bucket=bucket, Key=key)["Body"].read()
    except ClientError as exc:
        if exc.response["Error"]["Code"] in {"NoSuchKey", "404"}:
            log("object_gone", logging.WARNING, key=key)  # deleted before we got to it
            return "gone"
        raise

    try:
        invoice = parse_nfe(body)
    except NFeError as exc:
        return _reject(bucket, key, exc.code, str(exc), repo)

    created = repo.put_invoice(invoice, s3_key=key)
    failed = events.publish(
        aws["events"], [events.invoice_imported_entry(invoice, bus=cfg.event_bus)]
    )
    if failed:
        raise RuntimeError("EventBridge rejected the InvoiceImported event")  # retried by SQS
    outcome = "created" if created else "duplicate"
    log(f"invoice_{outcome}", key=key, access_key=invoice.access_key, items=len(invoice.items))
    return outcome


def _reject(bucket: str, key: str, code: str, message: str, repo: InvoiceRepository) -> str:
    cfg, s3 = settings(), clients()["s3"]
    target = cfg.rejected_prefix + key.split("/", 1)[-1]
    s3.copy_object(Bucket=bucket, Key=target, CopySource={"Bucket": bucket, "Key": key})
    s3.delete_object(Bucket=bucket, Key=key)
    repo.put_rejection(s3_key=key, code=code, message=message)
    log(
        "invoice_rejected",
        logging.WARNING,
        key=key,
        moved_to=target,
        error_code=code,
        reason=message,
    )
    return "rejected"
