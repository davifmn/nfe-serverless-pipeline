"""Parse and validate NF-e XML (layout 4.00) into plain dataclasses.

Accepts both a distributed ``nfeProc`` (the signed NF-e plus the SEFAZ authorization
protocol, which is what companies actually receive and archive) and a bare ``NFe``.

Untrusted XML is first scanned with expat and rejected if it declares a DTD or any
entity, which is what XXE (reading local files) and "billion laughs" (memory exhaustion)
need. Only then is it parsed with ElementTree. This keeps the Lambda package free of
third-party dependencies. Business validation goes beyond the schema:

* the access key check digit is recomputed;
* every field encoded in the access key (state, year/month, issuer CNPJ, model,
  series, number, emission type, random code) must match the invoice body;
* issuer and recipient CNPJ/CPF check digits are verified;
* the sum of the item values must equal the declared products total;
* when present, the authorization protocol must refer to the same access key.

The digital signature is not verified: that needs the ICP-Brasil certificate chain
and is out of scope for this importer.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from xml.etree.ElementTree import Element
from xml.parsers import expat

from .documents import is_valid_access_key, is_valid_cnpj, is_valid_cpf, split_access_key

NS = "http://www.portalfiscal.inf.br/nfe"
_N = {"n": NS}
MAX_XML_BYTES = 2 * 1024 * 1024
TOTAL_TOLERANCE = Decimal("0.01")


class NFeError(ValueError):
    """The document is not a valid NF-e. ``code`` is stable and machine-readable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Party:
    document: str  # CNPJ (14) or CPF (11), digits/letters only
    kind: str  # "cnpj" or "cpf"
    name: str
    trade_name: str = ""
    city: str = ""
    state: str = ""
    state_registration: str = ""


@dataclass(frozen=True)
class Item:
    item_number: int
    product_code: str
    description: str
    ncm: str
    cfop: str
    unit: str
    quantity: Decimal
    unit_price: Decimal
    total: Decimal


@dataclass(frozen=True)
class ParsedInvoice:
    access_key: str
    model: str
    series: int
    number: int
    issued_at: datetime
    issue_date: date  # the date as written by the issuer (fiscal month uses this)
    operation_nature: str
    direction: int  # 0 = inbound (entrada), 1 = outbound (saída)
    issuer: Party
    recipient: Party | None
    items: list[Item] = field(default_factory=list)
    products_total: Decimal = Decimal("0")
    discount_total: Decimal = Decimal("0")
    freight_total: Decimal = Decimal("0")
    invoice_total: Decimal = Decimal("0")
    authorization_protocol: str = ""
    status_code: int | None = None


def _find(el: Element, path: str) -> Element | None:
    return el.find("/".join(f"n:{p}" for p in path.split("/")), _N)


def _text(el: Element, path: str, *, required: bool = True, default: str = "") -> str:
    node = _find(el, path)
    if node is None or node.text is None or not node.text.strip():
        if required:
            raise NFeError("missing_field", f"required field <{path}> is missing")
        return default
    return node.text.strip()


def _decimal(el: Element, path: str, *, required: bool = True) -> Decimal:
    raw = _text(el, path, required=required, default="0")
    try:
        return Decimal(raw)
    except InvalidOperation:
        raise NFeError("invalid_number", f"<{path}> is not a number: {raw!r}") from None


def _int(el: Element, path: str) -> int:
    raw = _text(el, path)
    if not raw.isdigit():
        raise NFeError("invalid_number", f"<{path}> is not an integer: {raw!r}")
    return int(raw)


def _party(el: Element | None, tag: str, address_tag: str) -> Party | None:
    if el is None:
        return None
    cnpj = _text(el, "CNPJ", required=False)
    cpf = _text(el, "CPF", required=False)
    if cnpj:
        if not is_valid_cnpj(cnpj):
            raise NFeError("invalid_cnpj", f"{tag} CNPJ {cnpj} has invalid check digits")
        document, kind = cnpj.upper(), "cnpj"
    elif cpf:
        if not is_valid_cpf(cpf):
            raise NFeError("invalid_cpf", f"{tag} CPF {cpf} has invalid check digits")
        document, kind = cpf, "cpf"
    else:
        raise NFeError("missing_field", f"{tag} has neither CNPJ nor CPF")
    return Party(
        document=document,
        kind=kind,
        name=_text(el, "xNome"),
        trade_name=_text(el, "xFant", required=False),
        city=_text(el, f"{address_tag}/xMun", required=False),
        state=_text(el, f"{address_tag}/UF", required=False),
        state_registration=_text(el, "IE", required=False),
    )


class _UnsafeXML(Exception):
    pass


def _forbid(*_args) -> None:
    raise _UnsafeXML


def _reject_dtd(data: bytes) -> None:
    scanner = expat.ParserCreate()
    scanner.StartDoctypeDeclHandler = _forbid
    scanner.EntityDeclHandler = _forbid
    scanner.UnparsedEntityDeclHandler = _forbid
    scanner.ExternalEntityRefHandler = _forbid
    try:
        scanner.Parse(data, True)
    except _UnsafeXML:
        raise NFeError("unsafe_xml", "DTDs and entity declarations are not allowed") from None
    except expat.ExpatError as exc:
        raise NFeError("malformed_xml", f"not well-formed XML: {exc}") from None


def parse_nfe(xml: bytes | str) -> ParsedInvoice:
    data = xml.encode() if isinstance(xml, str) else xml
    if len(data) > MAX_XML_BYTES:
        raise NFeError("too_large", f"XML larger than {MAX_XML_BYTES // 1024} KiB")
    _reject_dtd(data)
    try:
        root = ET.fromstring(data)  # noqa: S314 - DTDs/entities already rejected above
    except ET.ParseError as exc:
        raise NFeError("malformed_xml", f"not well-formed XML: {exc}") from None

    if root.tag == f"{{{NS}}}nfeProc":
        nfe, protocol = _find(root, "NFe"), _find(root, "protNFe/infProt")
    elif root.tag == f"{{{NS}}}NFe":
        nfe, protocol = root, None
    else:
        raise NFeError("not_nfe", f"root element {root.tag!r} is not an NF-e")
    inf = _find(nfe, "infNFe") if nfe is not None else None
    if inf is None:
        raise NFeError("not_nfe", "missing <infNFe>")
    if inf.get("versao") != "4.00":
        raise NFeError("unsupported_version", f"layout {inf.get('versao')!r} (expected 4.00)")

    key = (inf.get("Id") or "").removeprefix("NFe")
    if not is_valid_access_key(key):
        raise NFeError("invalid_access_key", f"access key {key!r} is malformed or has a bad DV")

    ide = _find(inf, "ide")
    if ide is None:
        raise NFeError("missing_field", "missing <ide>")
    try:
        issued_at = datetime.fromisoformat(_text(ide, "dhEmi"))
    except ValueError:
        raw = _text(ide, "dhEmi")
        raise NFeError("invalid_date", f"<dhEmi> is not a date-time: {raw!r}") from None
    if issued_at.tzinfo is None:
        raise NFeError("invalid_date", "<dhEmi> must include a UTC offset")
    issuer = _party(_find(inf, "emit"), "issuer", "enderEmit")
    recipient = _party(_find(inf, "dest"), "recipient", "enderDest")
    if issuer is None:
        raise NFeError("missing_field", "missing <emit>")

    parts = split_access_key(key)
    expected = {
        "state_code": _text(ide, "cUF"),
        "year_month": issued_at.strftime("%y%m"),
        "cnpj": issuer.document if issuer.kind == "cnpj" else parts["cnpj"],
        "model": _text(ide, "mod"),
        "series": f"{_int(ide, 'serie'):03d}",
        "number": f"{_int(ide, 'nNF'):09d}",
        "emission_type": _text(ide, "tpEmis"),
        "random_code": f"{_int(ide, 'cNF'):08d}",
        "check_digit": _text(ide, "cDV"),
    }
    mismatched = [name for name, value in expected.items() if parts[name] != value]
    if mismatched:
        raise NFeError(
            "key_mismatch",
            "access key does not match the invoice body: " + ", ".join(sorted(mismatched)),
        )

    items = []
    for det in inf.findall("n:det", _N):
        prod = _find(det, "prod")
        if prod is None:
            raise NFeError("missing_field", "item without <prod>")
        items.append(
            Item(
                item_number=int(det.get("nItem", "0")) if det.get("nItem", "").isdigit() else 0,
                product_code=_text(prod, "cProd"),
                description=_text(prod, "xProd"),
                ncm=_text(prod, "NCM"),
                cfop=_text(prod, "CFOP"),
                unit=_text(prod, "uCom"),
                quantity=_decimal(prod, "qCom"),
                unit_price=_decimal(prod, "vUnCom"),
                total=_decimal(prod, "vProd"),
            )
        )
    if not items:
        raise NFeError("no_items", "the invoice has no items (<det>)")
    if len({i.item_number for i in items}) != len(items):
        raise NFeError("duplicate_item", "two items share the same nItem")

    totals = _find(inf, "total/ICMSTot")
    if totals is None:
        raise NFeError("missing_field", "missing <total/ICMSTot>")
    products_total = _decimal(totals, "vProd")
    items_sum = sum((i.total for i in items), Decimal("0"))
    if abs(items_sum - products_total) > TOTAL_TOLERANCE:
        raise NFeError(
            "total_mismatch",
            f"items add up to {items_sum} but <vProd> declares {products_total}",
        )

    authorization, status = "", None
    if protocol is not None:
        if _text(protocol, "chNFe") != key:
            raise NFeError("protocol_mismatch", "authorization protocol is for another NF-e")
        authorization = _text(protocol, "nProt", required=False)
        status = _int(protocol, "cStat")

    return ParsedInvoice(
        access_key=key,
        model=expected["model"],
        series=int(expected["series"]),
        number=int(expected["number"]),
        issued_at=issued_at,
        issue_date=issued_at.date(),
        operation_nature=_text(ide, "natOp"),
        direction=_int(ide, "tpNF"),
        issuer=issuer,
        recipient=recipient,
        items=items,
        products_total=products_total,
        discount_total=_decimal(totals, "vDesc", required=False),
        freight_total=_decimal(totals, "vFrete", required=False),
        invoice_total=_decimal(totals, "vNF"),
        authorization_protocol=authorization,
        status_code=status,
    )
