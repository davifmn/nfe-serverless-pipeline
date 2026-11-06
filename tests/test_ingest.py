import json
from unittest import mock

from botocore.exceptions import ClientError
from conftest import BUCKET, make_xml, s3_event, sqs_batch

from nfe_pipeline.handlers import ingest


def upload(aws, key, body):
    aws["s3"].put_object(Bucket=BUCKET, Key=key, Body=body)


def test_valid_invoice_is_stored(aws):
    xml = make_xml()
    upload(aws, "incoming/nota.xml", xml)
    assert ingest.handler(sqs_batch(s3_event("incoming/nota.xml", len(xml))), None) == {
        "batchItemFailures": []
    }
    items = aws["table"].scan()["Items"]
    assert len(items) == 1
    item = items[0]
    assert item["PK"].startswith("INVOICE#") and item["GSI1PK"] == "ISSUER#11222333000181"
    assert item["invoice_total"] == "387.00"
    assert item["recipient"]["document"] == "12ABC34501DE35"


def test_duplicate_delivery_is_a_no_op(aws):
    upload(aws, "incoming/nota.xml", make_xml())
    record = s3_event("incoming/nota.xml")
    assert ingest.process_object(bucket=BUCKET, key="incoming/nota.xml", size=10) == "created"
    assert ingest.handler(sqs_batch(record), None)["batchItemFailures"] == []
    assert ingest.process_object(bucket=BUCKET, key="incoming/nota.xml", size=10) == "duplicate"
    assert aws["table"].scan()["Count"] == 1


def test_invalid_document_is_moved_and_recorded(aws):
    upload(aws, "incoming/bad.xml", b"<not-xml")
    result = ingest.handler(sqs_batch(s3_event("incoming/bad.xml")), None)
    assert result["batchItemFailures"] == []  # permanent error: do not retry
    keys = [o["Key"] for o in aws["s3"].list_objects_v2(Bucket=BUCKET)["Contents"]]
    assert keys == ["rejected/bad.xml"]
    rejection = aws["table"].scan()["Items"][0]
    assert (
        rejection["PK"] == "REJECTED#incoming/bad.xml"
        and rejection["error_code"] == "malformed_xml"
    )


def test_tampered_check_digit_is_rejected(aws):
    xml = make_xml()
    key = xml.split(b'Id="NFe')[1][:44]
    tampered = xml.replace(key, key[:-1] + bytes(str((int(key[-1:]) + 1) % 10), "ascii"))
    upload(aws, "incoming/t.xml", tampered)
    assert ingest.process_object(bucket=BUCKET, key="incoming/t.xml", size=10) == "rejected"
    assert aws["table"].scan()["Items"][0]["error_code"] == "invalid_access_key"


def test_oversized_object_is_rejected_without_download(aws):
    upload(aws, "incoming/huge.xml", b"x")
    assert (
        ingest.process_object(bucket=BUCKET, key="incoming/huge.xml", size=50 * 1024 * 1024)
        == "rejected"
    )


def test_url_encoded_keys_are_decoded(aws):
    upload(aws, "incoming/nota fiscal 1.xml", make_xml())
    record = s3_event("incoming/nota+fiscal+1.xml")
    assert ingest.handler(sqs_batch(record), None)["batchItemFailures"] == []
    assert aws["table"].scan()["Count"] == 1


def test_transient_errors_fail_only_their_message(aws):
    upload(aws, "incoming/a.xml", make_xml(number=1))
    upload(aws, "incoming/b.xml", make_xml(number=2))
    real = ingest.InvoiceRepository.put_invoice
    throttled = ClientError(
        {"Error": {"Code": "ProvisionedThroughputExceededException"}}, "PutItem"
    )

    def flaky(self, invoice, *, s3_key):
        if s3_key.endswith("b.xml"):
            raise throttled
        return real(self, invoice, s3_key=s3_key)

    with mock.patch.object(ingest.InvoiceRepository, "put_invoice", flaky):
        result = ingest.handler(
            sqs_batch(s3_event("incoming/a.xml"), s3_event("incoming/b.xml")), None
        )
    assert result == {"batchItemFailures": [{"itemIdentifier": "msg-incoming/b.xml"}]}
    assert aws["table"].scan()["Count"] == 1


def test_s3_test_events_and_garbage_are_ignored(aws):
    test_event = {"messageId": "t", "body": json.dumps({"Event": "s3:TestEvent"})}
    garbage = {"messageId": "g", "body": "not json"}
    assert ingest.handler(sqs_batch(test_event, garbage), None)["batchItemFailures"] == []


def test_deleted_object_is_skipped(aws):
    assert ingest.process_object(bucket=BUCKET, key="incoming/gone.xml", size=10) == "gone"


def test_event_is_published(aws):
    upload(aws, "incoming/nota.xml", make_xml())
    with mock.patch.object(ingest.events, "publish", return_value=0) as publish:
        ingest.process_object(bucket=BUCKET, key="incoming/nota.xml", size=10)
    entry = publish.call_args.args[1][0]
    assert entry["DetailType"] == "InvoiceImported" and entry["EventBusName"] == "nfe-events-test"
    assert json.loads(entry["Detail"])["invoice_total"] == "387.00"


def test_event_failure_is_retried(aws):
    upload(aws, "incoming/nota.xml", make_xml())
    with mock.patch.object(ingest.events, "publish", return_value=1):
        result = ingest.handler(sqs_batch(s3_event("incoming/nota.xml")), None)
    assert len(result["batchItemFailures"]) == 1
    # On retry the invoice is a duplicate, but the event is still sent (at-least-once).
    with mock.patch.object(ingest.events, "publish", return_value=0) as publish:
        assert (
            ingest.handler(sqs_batch(s3_event("incoming/nota.xml")), None)["batchItemFailures"]
            == []
        )
    publish.assert_called_once()
