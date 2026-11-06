import json
from datetime import datetime
from decimal import Decimal

import boto3
import pytest
from moto import mock_aws
from nfe_samples import BRT, SampleCompany, SampleItem, build_nfe_xml

from nfe_pipeline import config

BUCKET, TABLE, BUS = "nfe-inbox-test", "nfe-invoices-test", "nfe-events-test"
ISSUER = SampleCompany("11222333000181", "Torrefação Teste Ltda", "Teste", "Belo Horizonte", "MG")
BUYER = SampleCompany("12ABC34501DE35", "Cafeteria Alfa Ltda", "Alfa", "São Paulo", "SP")
ITEM = SampleItem(
    "TOR-1KG", "CAFE TORRADO EM GRAOS 1KG", "09012100", Decimal("3"), Decimal("129.00"), "KG"
)


def make_xml(number=1, when=None, **kwargs) -> bytes:
    return build_nfe_xml(
        ISSUER,
        BUYER,
        [ITEM],
        number=number,
        issued_at=when or datetime(2026, 10, 15, 14, 30, tzinfo=BRT),
        **kwargs,
    )


def create_table(dynamodb):
    """Same keys as infra/modules/ingestion/dynamodb.tf."""
    dynamodb.create_table(
        TableName=TABLE,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": n, "AttributeType": "S"} for n in ("PK", "SK", "GSI1PK", "GSI1SK")
        ],
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "GSI1",
                "KeySchema": [
                    {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                    {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    )


@pytest.fixture
def aws(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("TABLE_NAME", TABLE)
    monkeypatch.setenv("BUCKET_NAME", BUCKET)
    monkeypatch.setenv("EVENT_BUS_NAME", BUS)
    config.settings.cache_clear()
    config.clients.cache_clear()
    with mock_aws():
        s3 = boto3.client("s3")
        s3.create_bucket(Bucket=BUCKET)
        create_table(boto3.client("dynamodb"))
        boto3.client("events").create_event_bus(Name=BUS)
        yield {"s3": s3, "table": boto3.resource("dynamodb").Table(TABLE)}
    config.settings.cache_clear()
    config.clients.cache_clear()


def s3_event(key: str, size: int = 1000) -> dict:
    """An SQS record whose body is an S3 ObjectCreated notification, as AWS delivers it."""
    body = {
        "Records": [
            {
                "eventName": "ObjectCreated:Put",
                "s3": {"bucket": {"name": BUCKET}, "object": {"key": key, "size": size}},
            }
        ]
    }
    return {"messageId": f"msg-{key}", "body": json.dumps(body)}


def sqs_batch(*records) -> dict:
    return {"Records": list(records)}
