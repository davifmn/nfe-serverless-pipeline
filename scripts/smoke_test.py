"""Smoke test of a deployed environment: upload one synthetic NF-e, then query it via the API.

python scripts/smoke_test.py --bucket <inbox> --api-url <url> --api-key-id <id>
"""

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import boto3

sys.path[:0] = [str(Path(__file__).parents[1] / "src"), str(Path(__file__).parents[1] / "tests")]
from nfe_samples import BRT, SampleCompany, SampleItem, build_nfe_xml  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--api-key-id", required=True)
    args = parser.parse_args()

    api_key = boto3.client("apigateway").get_api_key(apiKey=args.api_key_id, includeValue=True)[
        "value"
    ]
    issuer = SampleCompany("11222333000181", "Smoke Test Ltda", "Smoke", "Belo Horizonte", "MG")
    number = int(time.time()) % 900_000_000
    xml = build_nfe_xml(
        issuer,
        "52998224725",
        [SampleItem("SMOKE", "CAFE TORRADO 1KG", "09012100", Decimal("1"), Decimal("99.90"), "KG")],
        number=number,
        issued_at=datetime.now(BRT),
    )
    key = xml.split(b'Id="NFe')[1][:44].decode()
    boto3.client("s3").put_object(Bucket=args.bucket, Key=f"incoming/smoke/{key}.xml", Body=xml)
    print("uploaded", key)

    url = f"{args.api_url.rstrip('/')}/invoices/{key}"
    for attempt in range(30):
        request = urllib.request.Request(url, headers={"x-api-key": api_key})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
                body = json.loads(response.read())
                print("found after", attempt * 2, "s:", body["invoice_total"])
                return 0
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
        time.sleep(2)
    print("invoice did not show up in 60 s", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
