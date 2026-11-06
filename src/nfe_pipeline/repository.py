"""DynamoDB access, single-table design.

Access patterns, and the keys that serve each one:

* one invoice by access key: ``PK = INVOICE#<key>``, ``SK = META``
* an issuer's invoices in a date range: index GSI1, ``GSI1PK = ISSUER#<cnpj>``,
  ``GSI1SK`` between ``<from>`` and ``<to>`` (it starts with the issue date)
* rejected uploads, for audit and reprocessing: ``PK = REJECTED#<s3 key>``, ``SK = <error code>``

Writes are conditional (``attribute_not_exists(PK)``), so an at-least-once SQS delivery or
a re-uploaded file never creates duplicates and never overwrites what is already stored.
Money is stored as strings, so the exact decimal value survives (DynamoDB numbers would
work too, but strings keep the API output identical to the XML).
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from botocore.exceptions import ClientError

from .parser import ParsedInvoice

GSI1 = "GSI1"


def invoice_item(invoice: ParsedInvoice, *, s3_key: str) -> dict[str, Any]:
    issuer = invoice.issuer
    recipient = invoice.recipient
    return {
        "PK": f"INVOICE#{invoice.access_key}",
        "SK": "META",
        "GSI1PK": f"ISSUER#{issuer.document}",
        "GSI1SK": f"{invoice.issue_date.isoformat()}#{invoice.access_key}",
        "type": "invoice",
        "access_key": invoice.access_key,
        "model": invoice.model,
        "series": invoice.series,
        "number": invoice.number,
        "issued_at": invoice.issued_at.isoformat(),
        "issue_date": invoice.issue_date.isoformat(),
        "operation_nature": invoice.operation_nature,
        "issuer": asdict(issuer),
        "recipient": asdict(recipient) if recipient else None,
        "products_total": str(invoice.products_total),
        "freight_total": str(invoice.freight_total),
        "discount_total": str(invoice.discount_total),
        "invoice_total": str(invoice.invoice_total),
        "status_code": invoice.status_code,
        "authorization_protocol": invoice.authorization_protocol,
        "items": [
            {
                **asdict(item),
                "quantity": str(item.quantity),
                "unit_price": str(item.unit_price),
                "total": str(item.total),
            }
            for item in invoice.items
        ],
        "source_object": s3_key,
        "imported_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


class InvoiceRepository:
    def __init__(self, table) -> None:
        self.table = table  # boto3 DynamoDB Table resource

    def put_invoice(self, invoice: ParsedInvoice, *, s3_key: str) -> bool:
        """Store the invoice. Returns False if it was already there (duplicate delivery)."""
        try:
            self.table.put_item(
                Item=invoice_item(invoice, s3_key=s3_key),
                ConditionExpression="attribute_not_exists(PK)",
            )
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def put_rejection(self, *, s3_key: str, code: str, message: str) -> None:
        self.table.put_item(
            Item={
                "PK": f"REJECTED#{s3_key}",
                "SK": code,
                "type": "rejection",
                "source_object": s3_key,
                "error_code": code,
                "message": message[:1000],
                "rejected_at": datetime.now(UTC).isoformat(timespec="seconds"),
            }
        )

    def get_invoice(self, access_key: str) -> dict[str, Any] | None:
        response = self.table.get_item(Key={"PK": f"INVOICE#{access_key}", "SK": "META"})
        return _public(response.get("Item"))

    def invoices_by_issuer(
        self,
        cnpj: str,
        *,
        date_from: str,
        date_to: str,
        limit: int = 50,
        cursor: dict | None = None,
    ) -> tuple[list[dict[str, Any]], dict | None]:
        from boto3.dynamodb.conditions import Key

        kwargs: dict[str, Any] = {
            "IndexName": GSI1,
            # "~" sorts after "#<key>", so the whole last day is included.
            "KeyConditionExpression": Key("GSI1PK").eq(f"ISSUER#{cnpj}")
            & Key("GSI1SK").between(date_from, f"{date_to}~"),
            "Limit": limit,
            "ScanIndexForward": False,  # newest first
        }
        if cursor:
            kwargs["ExclusiveStartKey"] = cursor
        response = self.table.query(**kwargs)
        return [_summary(i) for i in response.get("Items", [])], response.get("LastEvaluatedKey")


_INTERNAL = {"PK", "SK", "GSI1PK", "GSI1SK", "type"}


def _public(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {k: _plain(v) for k, v in item.items() if k not in _INTERNAL}


def _summary(item: dict[str, Any]) -> dict[str, Any]:
    full = _public(item) or {}
    return {
        k: full.get(k)
        for k in ("access_key", "number", "series", "issue_date", "invoice_total", "status_code")
    } | {"recipient": (full.get("recipient") or {}).get("name")}


def _plain(value: Any) -> Any:
    """DynamoDB returns numbers as Decimal; make them JSON-friendly ints."""
    from decimal import Decimal

    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else str(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value
