import base64
import json
from datetime import datetime

import pytest
from conftest import BUCKET, ISSUER, make_xml
from nfe_samples import BRT

from nfe_pipeline.handlers import api, ingest


def call(resource, path=None, query=None, method="GET"):
    response = api.handler(
        {
            "resource": resource,
            "httpMethod": method,
            "pathParameters": path,
            "queryStringParameters": query,
        },
        None,
    )
    return response["statusCode"], json.loads(response["body"])


@pytest.fixture
def stored(aws):
    keys = []
    for n, day in enumerate([3, 10, 20, 25], start=1):
        xml = make_xml(number=n, when=datetime(2026, 10, day, 9, 0, tzinfo=BRT))
        aws["s3"].put_object(Bucket=BUCKET, Key=f"incoming/{n}.xml", Body=xml)
        ingest.process_object(bucket=BUCKET, key=f"incoming/{n}.xml", size=len(xml))
        keys.append(xml.split(b'Id="NFe')[1][:44].decode())
    return keys


def test_health(aws):
    assert call("/health") == (200, {"status": "ok"})


def test_get_invoice(stored):
    status, body = call("/invoices/{access_key}", {"access_key": stored[0]})
    assert status == 200
    assert body["access_key"] == stored[0] and body["items"][0]["ncm"] == "09012100"
    assert "PK" not in body and "GSI1PK" not in body  # storage details stay internal


def test_get_invoice_errors(stored):
    assert call("/invoices/{access_key}", {"access_key": "123"})[0] == 400
    missing = stored[0][:-1] + str((int(stored[0][-1]) + 1) % 10)
    assert call("/invoices/{access_key}", {"access_key": missing})[0] == 400  # bad DV
    from nfe_pipeline.documents import build_access_key

    unknown = build_access_key(
        state_code="31",
        year_month="2610",
        cnpj=ISSUER.cnpj,
        model="55",
        series=9,
        number=999,
        emission_type=1,
        random_code="1",
    )
    assert call("/invoices/{access_key}", {"access_key": unknown})[0] == 404


def test_issuer_invoices_by_date_range_newest_first(stored):
    status, body = call(
        "/issuers/{cnpj}/invoices",
        {"cnpj": "11.222.333/0001-81"},
        {"from": "2026-10-10", "to": "2026-10-20"},
    )
    assert status == 200
    assert [i["issue_date"] for i in body["items"]] == ["2026-10-20", "2026-10-10"]
    assert body["next_cursor"] is None


def test_pagination_with_cursor(stored):
    seen, cursor = [], None
    for _ in range(5):
        query = {"limit": "1"} | ({"cursor": cursor} if cursor else {})
        _, body = call("/issuers/{cnpj}/invoices", {"cnpj": ISSUER.cnpj}, query)
        seen += [i["access_key"] for i in body["items"]]
        cursor = body["next_cursor"]
        if not cursor:
            break
    assert sorted(seen) == sorted(stored)


@pytest.mark.parametrize(
    ("path", "query"),
    [
        ({"cnpj": "11222333000182"}, None),
        ({"cnpj": ISSUER.cnpj}, {"from": "yesterday"}),
        ({"cnpj": ISSUER.cnpj}, {"limit": "1000"}),
        ({"cnpj": ISSUER.cnpj}, {"from": "2026-12-01", "to": "2026-01-01"}),
        ({"cnpj": ISSUER.cnpj}, {"cursor": base64.urlsafe_b64encode(b"[1]").decode()}),
        ({"cnpj": ISSUER.cnpj}, {"cursor": "%%%"}),
    ],
)
def test_issuer_query_validation(aws, path, query):
    assert call("/issuers/{cnpj}/invoices", path, query)[0] == 400


def test_unknown_route_and_method(aws):
    assert call("/nope")[0] == 404
    assert call("/health", method="DELETE")[0] == 405
