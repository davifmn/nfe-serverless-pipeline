"""Query Lambda behind API Gateway (REST API, Lambda proxy integration).

    GET /health
    GET /invoices/{access_key}
    GET /issuers/{cnpj}/invoices?from=YYYY-MM-DD&to=YYYY-MM-DD&limit=50&cursor=...

Authentication (API keys, usage plan with rate limits) is enforced by API Gateway before
the function runs. This code validates input and maps errors to HTTP status codes.
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import date

from ..config import clients
from ..documents import is_valid_access_key, is_valid_cnpj, only_document_chars
from ..logs import log
from ..repository import InvoiceRepository

MAX_PAGE = 100


def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def _error(status: int, message: str) -> dict:
    return _response(status, {"error": message})


def _encode_cursor(key: dict | None) -> str | None:
    return base64.urlsafe_b64encode(json.dumps(key).encode()).decode() if key else None


def _decode_cursor(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        value = json.loads(base64.urlsafe_b64decode(raw.encode()))
    except (binascii.Error, ValueError):
        raise ValueError("invalid cursor") from None
    if not isinstance(value, dict):
        raise ValueError("invalid cursor")
    return value


def handler(event: dict, context) -> dict:
    route = event.get("resource", "")
    method = event.get("httpMethod", "GET")
    params = event.get("pathParameters") or {}
    query = event.get("queryStringParameters") or {}
    if method != "GET":
        return _error(405, "method not allowed")

    if route == "/health":
        return _response(200, {"status": "ok"})

    repo = InvoiceRepository(clients()["table"])

    if route == "/invoices/{access_key}":
        key = (params.get("access_key") or "").upper()
        if not is_valid_access_key(key):
            return _error(400, "invalid access key (44 characters with a valid check digit)")
        invoice = repo.get_invoice(key)
        return _response(200, invoice) if invoice else _error(404, "invoice not found")

    if route == "/issuers/{cnpj}/invoices":
        cnpj = only_document_chars(params.get("cnpj", ""))
        if not is_valid_cnpj(cnpj):
            return _error(400, "invalid CNPJ")
        try:
            date_from = date.fromisoformat(query.get("from", "2000-01-01")).isoformat()
            date_to = date.fromisoformat(query.get("to", "2999-12-31")).isoformat()
            limit = int(query.get("limit", 50))
            cursor = _decode_cursor(query.get("cursor"))
        except ValueError as exc:
            return _error(400, str(exc))
        if not 1 <= limit <= MAX_PAGE:
            return _error(400, f"limit must be between 1 and {MAX_PAGE}")
        if date_from > date_to:
            return _error(400, "'from' is after 'to'")
        items, last = repo.invoices_by_issuer(
            cnpj, date_from=date_from, date_to=date_to, limit=limit, cursor=cursor
        )
        log("issuer_query", cnpj=cnpj, returned=len(items))
        return _response(200, {"items": items, "next_cursor": _encode_cursor(last)})

    return _error(404, "route not found")
