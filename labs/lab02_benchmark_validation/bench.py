"""Lab 02 — đo chi phí validate hóa đơn bằng nhiều cách (tái tạo xu hướng của Module 06).

Chạy:  python bench.py              (vài chục giây)
       python bench.py --lines 100  (hóa đơn 100 dòng)
"""
import argparse
import json
import statistics
import sys
import timeit
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "lab01_invoice_models"))
from invoice import Invoice  # noqa: E402
from pydantic import TypeAdapter  # noqa: E402


def make_payload(n_lines: int) -> bytes:
    lines, before, tax = [], 0, 0
    rates = ["0", "5", "8", "10"]
    for i in range(n_lines):
        q, p, r = (i % 5) + 1, 1000 * (i % 7 + 1), rates[i % 4]
        lines.append({"name": f"Mặt hàng {i}", "quantity": str(q), "unit_price": p, "vat_rate": r, "amount": q * p})
        before += q * p
        tax += int((q * p * int(r) + 50) // 100)                     # half-up cho số nguyên dương
    return json.dumps({"seller_tax_code": "0100109106", "buyer": {"name": "Cty Sông Hậu"},
                       "issued_at": "2026-10-13T09:00:00+07:00", "lines": lines,
                       "total_before_tax": before, "total_tax": tax, "total": before + tax},
                      ensure_ascii=False).encode()


def bench(fn, number=2000, repeat=7):
    """Trả về µs/lần, lấy MIN của các lần lặp (ít nhiễu nhất, xem Module 06)."""
    times = timeit.repeat(fn, number=number, repeat=repeat)
    return min(times) / number * 1e6, statistics.median(times) / number * 1e6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", type=int, default=12)
    a = ap.parse_args()
    raw = make_payload(a.lines)
    Invoice.model_validate_json(raw)                                  # kiểm payload hợp lệ
    data = json.loads(raw)
    ta = TypeAdapter(list[Invoice])
    raw_list = b"[" + raw + b"]"

    cases = {
        "json.loads (chỉ parse)": lambda: json.loads(raw),
        "model_validate_json(bytes)": lambda: Invoice.model_validate_json(raw),
        "json.loads + model_validate": lambda: Invoice.model_validate(json.loads(raw)),
        "model_validate(dict có sẵn)": lambda: Invoice.model_validate(data),
        "TypeAdapter(list[Invoice]) dùng lại": lambda: ta.validate_json(raw_list),
        "TypeAdapter(list[Invoice]) tạo mới mỗi lần": lambda: TypeAdapter(list[Invoice]).validate_json(raw_list),
        "model_dump_json": (lambda inv=Invoice.model_validate_json(raw): inv.model_dump_json()),
    }
    print(f"Hóa đơn {a.lines} dòng, {len(raw)} byte")
    print(f"{'cách':45s} {'min µs':>9s} {'median µs':>10s}")
    out = {}
    for name, fn in cases.items():
        n = 200 if "tạo mới" in name else 2000
        mn, md = bench(fn, number=n)
        out[name] = mn
        print(f"{name:45s} {mn:9.1f} {md:10.1f}")
    base = out["model_validate_json(bytes)"]
    print(f"\njson.loads + model_validate chậm hơn model_validate_json {out['json.loads + model_validate'] / base:.2f}×")
    print(f"TypeAdapter tạo mới mỗi lần chậm hơn dùng lại "
          f"{out['TypeAdapter(list[Invoice]) tạo mới mỗi lần'] / out['TypeAdapter(list[Invoice]) dùng lại']:.1f}×")


if __name__ == "__main__":
    main()
