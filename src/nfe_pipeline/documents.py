"""Check digits of Brazilian fiscal identifiers: NF-e access key, CNPJ and CPF.

All three use a modulo-11 check digit with cyclic weights. The CNPJ functions also
accept the alphanumeric CNPJ that the Receita Federal started issuing in July 2026
(IN RFB nº 2.229/2024): the first 12 positions may be letters, each character is
valued as ``ord(char) - 48`` (so digits keep their value and "A" counts as 17), and
the two check digits stay numeric.
"""

from __future__ import annotations

import re

_CNPJ_RE = re.compile(r"^[0-9A-Z]{12}[0-9]{2}$")
_ACCESS_KEY_RE = re.compile(r"^[0-9]{6}[0-9A-Z]{12}[0-9]{26}$")


def only_document_chars(value: str) -> str:
    """Strip formatting such as ``12.345.678/0001-95`` and upper-case letters."""
    return re.sub(r"[^0-9A-Za-z]", "", value or "").upper()


def _value(char: str) -> int:
    return ord(char) - 48


def _mod11_digit(base: str, weights: list[int]) -> int:
    total = sum(_value(c) * w for c, w in zip(base, weights, strict=True))
    remainder = total % 11
    return 0 if remainder < 2 else 11 - remainder


# --- NF-e access key (chave de acesso) -------------------------------------------------
# 44 characters: cUF(2) AAMM(4) CNPJ(14) mod(2) serie(3) nNF(9) tpEmis(1) cNF(8) cDV(1)


def access_key_check_digit(first_43: str) -> int:
    """Weights 2..9 repeat from the rightmost character leftwards."""
    weights = [2 + (i % 8) for i in range(len(first_43))][::-1]
    return _mod11_digit(first_43, weights)


def is_valid_access_key(key: str) -> bool:
    if not _ACCESS_KEY_RE.match(key or ""):
        return False
    return access_key_check_digit(key[:43]) == int(key[43])


def build_access_key(
    *,
    state_code: str,
    year_month: str,
    cnpj: str,
    model: str,
    series: int,
    number: int,
    emission_type: int,
    random_code: str,
) -> str:
    base = (
        f"{state_code:0>2}{year_month}{cnpj}{model:0>2}{series:03d}{number:09d}"
        f"{emission_type}{random_code:0>8}"
    )
    if len(base) != 43:
        raise ValueError(f"access key base must have 43 characters, got {len(base)}")
    return base + str(access_key_check_digit(base))


def split_access_key(key: str) -> dict[str, str]:
    return {
        "state_code": key[0:2],
        "year_month": key[2:6],
        "cnpj": key[6:20],
        "model": key[20:22],
        "series": key[22:25],
        "number": key[25:34],
        "emission_type": key[34],
        "random_code": key[35:43],
        "check_digit": key[43],
    }


# --- CNPJ ------------------------------------------------------------------------------

_CNPJ_W1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_CNPJ_W2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]


def cnpj_check_digits(first_12: str) -> str:
    d1 = _mod11_digit(first_12, _CNPJ_W1)
    d2 = _mod11_digit(first_12 + str(d1), _CNPJ_W2)
    return f"{d1}{d2}"


def is_valid_cnpj(value: str) -> bool:
    cnpj = only_document_chars(value)
    if not _CNPJ_RE.match(cnpj) or len(set(cnpj)) == 1:
        return False
    return cnpj_check_digits(cnpj[:12]) == cnpj[12:]


# --- CPF -------------------------------------------------------------------------------


def cpf_check_digits(first_9: str) -> str:
    d1 = _mod11_digit(first_9, list(range(10, 1, -1)))
    d2 = _mod11_digit(first_9 + str(d1), list(range(11, 1, -1)))
    return f"{d1}{d2}"


def is_valid_cpf(value: str) -> bool:
    cpf = only_document_chars(value)
    if not re.fullmatch(r"[0-9]{11}", cpf) or len(set(cpf)) == 1:
        return False
    return cpf_check_digits(cpf[:9]) == cpf[9:]


def format_cnpj(cnpj: str) -> str:
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
