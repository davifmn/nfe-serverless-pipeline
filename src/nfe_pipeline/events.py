"""Domain events on EventBridge, so other teams can react without coupling to this service."""

from __future__ import annotations

import json

from .parser import ParsedInvoice

SOURCE = "nfe.pipeline"


def invoice_imported_entry(invoice: ParsedInvoice, *, bus: str) -> dict:
    return {
        "Source": SOURCE,
        "DetailType": "InvoiceImported",
        "EventBusName": bus,
        "Detail": json.dumps(
            {
                "access_key": invoice.access_key,
                "issuer": invoice.issuer.document,
                "recipient": invoice.recipient.document if invoice.recipient else None,
                "issue_date": invoice.issue_date.isoformat(),
                "invoice_total": str(invoice.invoice_total),
                "items": len(invoice.items),
            }
        ),
    }


def publish(client, entries: list[dict]) -> int:
    """Send in chunks of 10 (the PutEvents limit). Returns how many entries failed."""
    failed = 0
    for start in range(0, len(entries), 10):
        response = client.put_events(Entries=entries[start : start + 10])
        failed += response.get("FailedEntryCount", 0)
    return failed
