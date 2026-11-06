"""Generate synthetic but structurally valid NF-e XML (layout 4.00).

Used by the tests and by ``manage.py generate_sample_nfe``. Every company, CNPJ and CPF
is fictitious: the bases are random and only the check digits are computed, so the
documents pass validation without belonging to anyone. The theme is coffee: farms and
roasters selling green and roasted beans (NCM 0901.11.10 and 0901.21.00).
"""

from __future__ import annotations

import random
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from nfe_pipeline.documents import build_access_key, cnpj_check_digits, cpf_check_digits
from nfe_pipeline.parser import NS

ET.register_namespace("", NS)
BRT = timezone(timedelta(hours=-3))
STATE_CODES = {"MG": "31", "SP": "35", "RJ": "33", "PR": "41", "BA": "29", "ES": "32"}


@dataclass(frozen=True)
class SampleCompany:
    cnpj: str
    name: str
    trade_name: str
    city: str
    state: str


@dataclass(frozen=True)
class SampleItem:
    code: str
    description: str
    ncm: str
    quantity: Decimal
    unit_price: Decimal
    unit: str = "UN"


PRODUCTS = [
    ("CRU-BA-NAT", "CAFE CRU EM GRAO BOURBON AMARELO NATURAL SC 60KG", "09011110", "SC", "1650.00"),
    ("CRU-CT-CD", "CAFE CRU EM GRAO CATUAI CEREJA DESCASCADO SC 60KG", "09011110", "SC", "1480.00"),
    ("TOR-GE-250", "CAFE TORRADO EM GRAOS GEISHA 250G", "09012100", "UN", "89.90"),
    ("TOR-BA-1KG", "CAFE TORRADO EM GRAOS BOURBON AMARELO 1KG", "09012100", "KG", "129.00"),
    ("TOR-MN-500", "CAFE TORRADO E MOIDO MUNDO NOVO 500G", "09012100", "UN", "42.50"),
    ("TOR-AR-1KG", "CAFE TORRADO EM GRAOS ARARA FERMENTADO 1KG", "09012100", "KG", "164.00"),
]


def random_cnpj(rng: random.Random, *, alphanumeric: bool = False) -> str:
    alphabet = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ" if alphanumeric else "0123456789"
    base = "".join(rng.choice(alphabet) for _ in range(8)) + "0001"
    return base + cnpj_check_digits(base)


def random_cpf(rng: random.Random) -> str:
    base = "".join(rng.choice("0123456789") for _ in range(9))
    return base + cpf_check_digits(base)


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _sub(parent: ET.Element, tag: str, text: str | None = None, **attrs) -> ET.Element:
    el = ET.SubElement(parent, f"{{{NS}}}{tag}", attrs)
    if text is not None:
        el.text = text
    return el


def build_nfe_xml(
    issuer: SampleCompany,
    recipient: SampleCompany | str,
    items: list[SampleItem],
    *,
    number: int,
    issued_at: datetime,
    series: int = 1,
    random_code: str = "12345678",
    freight: Decimal = Decimal("0"),
    with_protocol: bool = True,
) -> bytes:
    """Return an NF-e XML. ``recipient`` is a company or a CPF string (consumer)."""
    state_code = STATE_CODES[issuer.state]
    key = build_access_key(
        state_code=state_code,
        year_month=issued_at.strftime("%y%m"),
        cnpj=issuer.cnpj,
        model="55",
        series=series,
        number=number,
        emission_type=1,
        random_code=random_code,
    )

    nfe = ET.Element(f"{{{NS}}}NFe")
    inf = _sub(nfe, "infNFe", versao="4.00", Id=f"NFe{key}")
    ide = _sub(inf, "ide")
    dest_state = recipient.state if isinstance(recipient, SampleCompany) else issuer.state
    for tag, value in [
        ("cUF", state_code),
        ("cNF", random_code),
        ("natOp", "VENDA DE MERCADORIA"),
        ("mod", "55"),
        ("serie", str(series)),
        ("nNF", str(number)),
        ("dhEmi", issued_at.isoformat(timespec="seconds")),
        ("tpNF", "1"),
        ("idDest", "1" if dest_state == issuer.state else "2"),
        ("tpEmis", "1"),
        ("cDV", key[-1]),
        ("tpAmb", "2"),  # 2 = homologation (test) environment
        ("finNFe", "1"),
    ]:
        _sub(ide, tag, value)

    emit = _sub(inf, "emit")
    _sub(emit, "CNPJ", issuer.cnpj)
    _sub(emit, "xNome", issuer.name)
    _sub(emit, "xFant", issuer.trade_name)
    address = _sub(emit, "enderEmit")
    _sub(address, "xMun", issuer.city)
    _sub(address, "UF", issuer.state)
    _sub(emit, "IE", "ISENTO")
    _sub(emit, "CRT", "1")

    dest = _sub(inf, "dest")
    if isinstance(recipient, SampleCompany):
        _sub(dest, "CNPJ", recipient.cnpj)
        _sub(dest, "xNome", recipient.name)
        address = _sub(dest, "enderDest")
        _sub(address, "xMun", recipient.city)
        _sub(address, "UF", recipient.state)
    else:
        _sub(dest, "CPF", recipient)
        _sub(dest, "xNome", "CONSUMIDOR FINAL")

    cfop = "5102" if dest_state == issuer.state else "6102"
    products_total = Decimal("0")
    for n, item in enumerate(items, start=1):
        total = (item.quantity * item.unit_price).quantize(Decimal("0.01"), ROUND_HALF_UP)
        products_total += total
        det = _sub(inf, "det", nItem=str(n))
        prod = _sub(det, "prod")
        for tag, value in [
            ("cProd", item.code),
            ("cEAN", "SEM GTIN"),
            ("xProd", item.description),
            ("NCM", item.ncm),
            ("CFOP", cfop),
            ("uCom", item.unit),
            ("qCom", f"{item.quantity:.4f}"),
            ("vUnCom", f"{item.unit_price:.10f}"),
            ("vProd", _money(total)),
        ]:
            _sub(prod, tag, value)

    tot = _sub(_sub(inf, "total"), "ICMSTot")
    for tag, value in [
        ("vProd", _money(products_total)),
        ("vFrete", _money(freight)),
        ("vDesc", "0.00"),
        ("vNF", _money(products_total + freight)),
    ]:
        _sub(tot, tag, value)

    if not with_protocol:
        return ET.tostring(nfe, encoding="utf-8", xml_declaration=True)

    proc = ET.Element(f"{{{NS}}}nfeProc", versao="4.00")
    proc.append(nfe)
    info = _sub(_sub(proc, "protNFe", versao="4.00"), "infProt")
    _sub(info, "tpAmb", "2")
    _sub(info, "chNFe", key)
    _sub(info, "dhRecbto", (issued_at + timedelta(seconds=4)).isoformat(timespec="seconds"))
    _sub(info, "nProt", f"1{state_code}{issued_at:%y}{number:010d}")
    _sub(info, "cStat", "100")
    _sub(info, "xMotivo", "Autorizado o uso da NF-e")
    return ET.tostring(proc, encoding="utf-8", xml_declaration=True)


ROASTERS = [
    ("Torrefação Serra Clara Ltda", "Serra Clara Cafés", "Belo Horizonte", "MG"),
    ("Café Pedra Alta Comércio Ltda", "Pedra Alta", "Poços de Caldas", "MG"),
    ("Grão do Planalto Torrefadora Ltda", "Grão do Planalto", "Franca", "SP"),
]
BUYERS = [
    ("Cafeteria Ponto Doce Ltda", "Ponto Doce", "São Paulo", "SP"),
    ("Empório Mantiqueira Ltda", "Empório Mantiqueira", "Belo Horizonte", "MG"),
    ("Bistrô Vila Rica Ltda", "Vila Rica", "Rio de Janeiro", "RJ"),
    ("Padaria Bom Grão Ltda", "Bom Grão", "Curitiba", "PR"),
]


def generate_batch(count: int, *, seed: int = 2026) -> list[tuple[str, bytes]]:
    """Return ``(filename, xml)`` pairs for a realistic batch of coffee sales."""
    rng = random.Random(seed)
    issuers = [SampleCompany(random_cnpj(rng), *r) for r in ROASTERS]
    # One buyer already has the new alphanumeric CNPJ format (issued since July 2026).
    buyers = [
        SampleCompany(random_cnpj(rng, alphanumeric=i == 0), *b) for i, b in enumerate(BUYERS)
    ]
    numbers = {c.cnpj: 1000 for c in issuers}
    start = datetime(2026, 1, 5, 9, 0, tzinfo=BRT)
    files = []
    for _ in range(count):
        issuer = rng.choice(issuers)
        numbers[issuer.cnpj] += 1
        recipient = rng.choice(buyers) if rng.random() < 0.8 else random_cpf(rng)
        lines = []
        for code, description, ncm, unit, price in rng.sample(PRODUCTS, rng.randint(1, 3)):
            qty = Decimal(rng.choice(["1", "2", "5", "10", "12", "24"]))
            if code.startswith("CRU"):
                qty = Decimal(rng.choice(["1", "2", "3"]))
            lines.append(SampleItem(code, description, ncm, qty, Decimal(price), unit))
        issued = start + timedelta(days=rng.randint(0, 290), minutes=rng.randint(0, 600))
        freight = Decimal(rng.choice(["0", "0", "35.00", "80.00"]))
        xml = build_nfe_xml(
            issuer,
            recipient,
            lines,
            number=numbers[issuer.cnpj],
            issued_at=issued,
            random_code=f"{rng.randrange(10**8):08d}",
            freight=freight,
        )
        files.append((f"NFe{xml_key(xml)}.xml", xml))
    return files


def xml_key(xml: bytes) -> str:
    start = xml.index(b'Id="NFe') + len(b'Id="NFe')
    return xml[start : start + 44].decode()
