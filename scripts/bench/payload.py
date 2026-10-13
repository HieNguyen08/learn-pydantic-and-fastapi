"""Sinh payload hóa đơn điện tử giả lập (tất định) cho benchmark.

Hóa đơn của Mekong Cloud: người bán (MST), người mua, n dòng hàng, tổng tiền.
Tiền là số nguyên VND; thuế suất là chuỗi trong {"0","5","8","10","KCT","KKKNT"}.
"""
from __future__ import annotations

import json
import random

VAT_RATES = ["0", "5", "8", "10", "KCT", "KKKNT"]
RATE_PCT = {"0": 0, "5": 5, "8": 8, "10": 10, "KCT": 0, "KKKNT": 0}
WEIGHTS = (31, 29, 23, 19, 17, 13, 7, 5, 3)


def mst_check_digit(first9: str) -> str:
    """Chữ số kiểm tra MST (cùng thuật toán với python-stdnum, stdnum.vn.mst)."""
    total = sum(w * int(c) for w, c in zip(WEIGHTS, first9))
    return str(10 - total % 11)  # có thể ra "10" → tiền tố đó không hợp lệ


def mst_is_valid(s: str) -> bool:
    if len(s) not in (10, 13) or not s.isdigit():
        return False
    if s[2:9] == "0000000" or (len(s) == 13 and s[-3:] == "000"):
        return False
    return s[9] == mst_check_digit(s[:9])


def make_mst(rng: random.Random) -> str:
    while True:
        first9 = "".join(str(rng.randint(0, 9)) for _ in range(9))
        c = mst_check_digit(first9)
        if len(c) == 1 and first9[2:9] != "0000000":
            return first9 + c


def make_invoice(n_lines: int, seed: int = 7) -> dict:
    rng = random.Random(seed * 1000 + n_lines)
    lines, before, tax = [], 0, 0
    for i in range(1, n_lines + 1):
        qty = rng.choice([1, 2, 3, 5, 10, 0.5, 1.5, 12])
        price = rng.choice([15_000, 27_500, 120_000, 350_000, 1_250_000, 9_990])
        rate = rng.choice(VAT_RATES[:4])
        amount = round(qty * price)
        lines.append({
            "line_no": i,
            "sku": f"SKU-{rng.randint(10000, 99999)}",
            "name": rng.choice(["Cà phê sữa đá", "Bánh mì thịt", "Phần mềm POS - gói tháng",
                                "Giấy in nhiệt 80mm", "Máy quét mã vạch", "Phí triển khai"]),
            "unit": rng.choice(["ly", "cái", "gói", "cuộn", "giờ"]),
            "quantity": qty,
            "unit_price": price,
            "vat_rate": rate,
            "amount": amount,
        })
        before += amount
        tax += round(amount * RATE_PCT[rate] / 100)
    return {
        "series": "1C26TMK",
        "number": rng.randint(1, 99_999_999),
        "seller_tax_code": make_mst(rng),
        "buyer": {
            "name": "Công ty TNHH Một Thành Viên Cà Phê Sông Hậu",
            "tax_code": make_mst(rng),
            "email": "ketoan@songhau.example.vn",
            "address": "12 Nguyễn Văn Cừ, Ninh Kiều, Cần Thơ",
        },
        "issued_at": "2026-10-13T11:45:00+07:00",
        "currency": "VND",
        "lines": lines,
        "total_before_tax": before,
        "total_tax": tax,
        "total": before + tax,
    }


def payload_bytes(n_lines: int) -> bytes:
    return json.dumps(make_invoice(n_lines), ensure_ascii=False).encode()


if __name__ == "__main__":
    for n in (1, 12, 50, 200):
        print(n, len(payload_bytes(n)), "bytes")
