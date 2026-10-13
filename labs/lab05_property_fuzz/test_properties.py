"""Lab 05 (phần 1) — property-based testing cho model hóa đơn của Lab 01.

Chạy:  pytest -q test_properties.py
"""
import sys
from decimal import Decimal
from pathlib import Path

from hypothesis import given, settings, strategies as st

sys.path.insert(0, str(Path(__file__).parents[1] / "lab01_invoice_models"))
from invoice import WEIGHTS, Invoice, line_tax  # noqa: E402


@st.composite
def mst(draw) -> str:
    first9 = draw(st.text(alphabet="0123456789", min_size=9, max_size=9).filter(lambda s: s[2:9] != "0000000"))
    check = 10 - sum(w * int(c) for w, c in zip(WEIGHTS, first9)) % 11
    from hypothesis import assume
    assume(check < 10)
    return first9 + str(check)


line = st.builds(
    lambda name, q, p, r: {"name": name, "quantity": str(q), "unit_price": p, "vat_rate": r,
                           "amount": int((Decimal(q) * p).to_integral_value(rounding="ROUND_HALF_UP"))},
    st.text(min_size=1, max_size=40).filter(lambda s: s.strip()),
    st.integers(1, 100), st.integers(0, 10**7), st.sampled_from(["0", "5", "8", "10", "KCT"]))


@st.composite
def invoice(draw) -> dict:
    lines = draw(st.lists(line, min_size=1, max_size=20))
    before = sum(l["amount"] for l in lines)
    tax = sum(line_tax(l["amount"], l["vat_rate"]) for l in lines)
    return {"seller_tax_code": draw(mst()), "buyer": {"name": "Cty A"}, "issued_at": "2026-10-13T09:00:00+07:00",
            "lines": lines, "total_before_tax": before, "total_tax": tax, "total": before + tax}


@settings(max_examples=200)
@given(invoice())
def test_hoa_don_sinh_ra_luon_hop_le_va_round_trip(data):
    inv = Invoice.model_validate(data)                                   # mọi hóa đơn hợp lệ được chấp nhận
    assert Invoice.model_validate_json(inv.model_dump_json()) == inv     # round-trip JSON


@settings(max_examples=200)
@given(invoice(), st.integers(1, 10**6))
def test_sua_tong_thi_bi_tu_choi(data, delta):
    from pydantic import ValidationError
    data = {**data, "total": data["total"] + delta}
    try:
        Invoice.model_validate(data)
    except ValidationError as e:
        assert any(x["type"] == "invoice_totals" for x in e.errors())
    else:
        raise AssertionError("tổng sai mà vẫn được chấp nhận")
