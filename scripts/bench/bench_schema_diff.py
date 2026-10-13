"""JSON Schema có diễn tả đủ validator của Pydantic không? (Module 05)

Sinh các biến thể đột biến của một hóa đơn hợp lệ, cho qua (a) jsonschema (Draft 2020-12) với schema
do Pydantic sinh và (b) chính model Pydantic ở chế độ lax và strict; đếm bốn ô đồng ý/bất đồng.
Chạy:  python bench_schema_diff.py → results/schema_diff.json
"""
import copy
import json
import random
from pathlib import Path

import jsonschema
from pydantic import ValidationError

from invoice_v2 import InvoiceIn

HERE = Path(__file__).parent
BASE = {"series": "1C26TMK", "number": 1024, "seller_tax_code": "0100233488",
        "buyer": {"name": "Công ty TNHH Cà Phê Sông Hậu", "tax_code": "0314409058"},
        "issued_at": "2026-10-13T11:45:00+07:00",
        "lines": [{"line_no": 1, "sku": "CF-01", "name": "Cà phê sữa đá", "unit": "ly", "quantity": 3,
                   "unit_price": 27500, "vat_rate": "8", "amount": 82500},
                  {"line_no": 2, "sku": "BM-02", "name": "Bánh mì", "unit": "cái", "quantity": 1.5,
                   "unit_price": 18353, "vat_rate": "5", "amount": 27530}],
        "total_before_tax": 110030, "total_tax": 7977, "total": 118007}

MUTATIONS = {
    "số → chuỗi số": lambda d, r: _set(d, r, ["number", "total", ("lines", 0, "unit_price")], lambda v: str(v)),
    "int → float .0": lambda d, r: _set(d, r, ["number", ("lines", 0, "line_no")], lambda v: float(v)),
    "thiếu trường": lambda d, r: _del(d, r, ["series", "buyer", ("lines", 1, "sku"), "issued_at"]),
    "trường lạ": lambda d, r: d.update({"discount": 1000}),
    "MST sai checksum": lambda d, r: d.update({"seller_tax_code": "0100233480"}),
    "MST có dấu gạch": lambda d, r: d["buyer"].update({"tax_code": "0314409058-002"}),
    "lệch tổng 1 đồng": lambda d, r: d.update({"total_tax": d["total_tax"] + 1}),
    "amount dòng sai": lambda d, r: d["lines"][1].update({"amount": 27529}),
    "thuế suất lạ": lambda d, r: d["lines"][0].update({"vat_rate": "7"}),
    "ngày không múi giờ": lambda d, r: d.update({"issued_at": "2026-10-13T11:45:00"}),
    "số lượng âm": lambda d, r: d["lines"][0].update({"quantity": -1}),
    "line_no trùng": lambda d, r: d["lines"][1].update({"line_no": 1}),
    "không đột biến": lambda d, r: None,
}


def _path_set(d, p, f):
    if isinstance(p, str):
        d[p] = f(d[p])
    else:
        x = d
        for k in p[:-1]:
            x = x[k]
        x[p[-1]] = f(x[p[-1]])


def _set(d, r, paths, f):
    _path_set(d, r.choice(paths), f)


def _del(d, r, paths):
    p = r.choice(paths)
    if isinstance(p, str):
        del d[p]
    else:
        x = d
        for k in p[:-1]:
            x = x[k]
        del x[p[-1]]


def main():
    schema = InvoiceIn.model_json_schema()
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    rng = random.Random(1)
    rows = []
    for name, mut in MUTATIONS.items():
        cnt = {"lax": {}, "strict": {}}
        for _ in range(40):
            d = copy.deepcopy(BASE)
            mut(d, rng)
            raw = json.dumps(d, ensure_ascii=False)
            js_ok = validator.is_valid(d)
            for mode in ("lax", "strict"):
                try:
                    InvoiceIn.model_validate_json(raw, strict=(mode == "strict"))
                    py_ok = True
                except ValidationError:
                    py_ok = False
                key = f"schema {'nhận' if js_ok else 'từ chối'} / pydantic {'nhận' if py_ok else 'từ chối'}"
                cnt[mode][key] = cnt[mode].get(key, 0) + 1
        rows.append(dict(mutation=name, **cnt))
        print(f"{name:20s} lax={cnt['lax']}  strict={cnt['strict']}")
    (HERE / "results" / "schema_diff.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
