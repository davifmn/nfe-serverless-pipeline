"""The whole pipeline wired the way Terraform wires it: S3 notification → SQS → ingest → API."""

import json

import boto3
from conftest import BUCKET, make_xml

from nfe_pipeline.handlers import api, ingest


def test_upload_to_query(aws):
    sqs = boto3.client("sqs")
    queue_url = sqs.create_queue(QueueName="nfe-ingest-test")["QueueUrl"]
    queue_arn = sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["QueueArn"])[
        "Attributes"
    ]["QueueArn"]
    aws["s3"].put_bucket_notification_configuration(
        Bucket=BUCKET,
        NotificationConfiguration={
            "QueueConfigurations": [
                {
                    "QueueArn": queue_arn,
                    "Events": ["s3:ObjectCreated:*"],
                    "Filter": {
                        "Key": {
                            "FilterRules": [
                                {"Name": "prefix", "Value": "incoming/"},
                                {"Name": "suffix", "Value": ".xml"},
                            ]
                        }
                    },
                }
            ]
        },
    )

    xml = make_xml(number=42)
    aws["s3"].put_object(Bucket=BUCKET, Key="incoming/2026/10/nota-42.xml", Body=xml)
    aws["s3"].put_object(Bucket=BUCKET, Key="incoming/readme.txt", Body=b"ignored by the filter")

    messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10)["Messages"]
    records = [m for m in messages if "Records" in json.loads(m["Body"])]
    assert len(records) == 1  # only the .xml under incoming/ was delivered
    event = {"Records": [{"messageId": m["MessageId"], "body": m["Body"]} for m in records]}
    assert ingest.handler(event, None) == {"batchItemFailures": []}

    key = xml.split(b'Id="NFe')[1][:44].decode()
    response = api.handler(
        {
            "resource": "/invoices/{access_key}",
            "httpMethod": "GET",
            "pathParameters": {"access_key": key},
        },
        None,
    )
    assert response["statusCode"] == 200
    assert json.loads(response["body"])["number"] == 42
