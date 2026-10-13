"""Kiểm thử Lab 01: ví dụ + thuộc tính (Hypothesis)."""
from decimal import Decimal
from fractions import Fraction

import pytest
from hypothesis import given, strategies as st
from pydantic import ValidationError

from invoice import WEIGHTS, Invoice, check_tax_code, line_tax


def valid_mst(first9: str) -> str | None:
    c = 10 - sum(w * int(x) for w, x in zip(WEIGHTS, first9)) % 11
    return first9 + str(c) if c < 10 and first9[2:9] != "0000000" else None


def make(**over):
    base = {"seller_tax_code": "0100109106", "buyer": {"name": "Cty Sông Hậu"},
            "issued_at": "2026-10-13T09:00:00+07:00",
            "lines": [{"name": "Cà phê", "quantity": "2", "unit_price": 29000, "vat_rate": "8", "amount": 58000},
                      {"name": "Bánh", "quantity": "1.5", "unit_price": 25000, "vat_rate": "10", "amount": 37500}],
            "total_before_tax": 95500, "total_tax": 8390, "total": 103890}
    base.update(over)
    return base


def test_hop_le():
    inv = Invoice.model_validate(make())
    assert inv.total == 103890


@pytest.mark.parametrize("over,err_type", [
    ({"seller_tax_code": "0100109107"}, "tax_code_checksum"),
    ({"seller_tax_code": "0100000000"}, "tax_code_format"),
    ({"total": 103891}, "invoice_totals"),
    ({"issued_at": "2026-10-13T09:00:00"}, "timezone_aware"),
    ({"extra_field": 1}, "extra_forbidden"),
    ({"total": "103890"}, "int_type"),                                # strict: không nhận chuỗi cho tiền
])
def test_loi(over, err_type):
    with pytest.raises(ValidationError) as ei:
        Invoice.model_validate(make(**over))
    assert err_type in {e["type"] for e in ei.value.errors()}


def test_json_round_trip():
    inv = Invoice.model_validate(make())
    assert Invoice.model_validate_json(inv.model_dump_json()) == inv


@given(st.text(alphabet="0123456789", min_size=9, max_size=9), st.integers(0, 9), st.integers(0, 9))
def test_mst_phat_hien_loi_mot_chu_so(first9, pos, digit):
    m = valid_mst(first9)
    if m is None:
        return
    assert check_tax_code(m) == m
    mutated = m[:pos] + str(digit) + m[pos + 1:]
    if mutated != m:
        with pytest.raises(Exception):
            check_tax_code(mutated)


@given(st.integers(0, 10**12), st.sampled_from(["0", "5", "8", "10"]))
def test_thue_lam_tron_nua_len(amount, rate):
    exact = Fraction(amount * int(rate), 100)
    got = line_tax(amount, rate)
    assert -Fraction(1, 2) < got - exact <= Fraction(1, 2)
