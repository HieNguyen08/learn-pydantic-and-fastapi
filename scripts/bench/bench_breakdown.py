"""Phân rã chi phí xử lý một hóa đơn và độ nhiễu của phép đo (Module 06).

Phần 1 — phân rã: parse JSON (jiter) → validate cấu trúc → quy tắc Python → serialize response.
Phần 2 — nhiễu: chạy cùng một phép đo trong 8 tiến trình riêng, so sánh độ phân tán của min và trung vị.
Chạy:  python bench_breakdown.py → results/breakdown.json
"""
import json
import statistics
import subprocess
import sys
import timeit
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))


def per_call_us(fn, repeat=11):
    t = timeit.Timer(fn)
    n, _ = t.autorange()
    xs = [x / n * 1e6 for x in t.repeat(repeat, n)]
    return min(xs), statistics.median(xs)


def breakdown():
    from pydantic_core import from_json

    from impls import _pydantic_v2_models
    from payload import payload_bytes
    schema, full = _pydantic_v2_models("schema"), _pydantic_v2_models("full")
    out = []
    for n in (1, 12, 50, 200):
        raw = payload_bytes(n)
        inv = full.model_validate_json(raw)
        parse = per_call_us(lambda: from_json(raw))[0]
        v_schema = per_call_us(lambda: schema.model_validate_json(raw))[0]
        v_full = per_call_us(lambda: full.model_validate_json(raw))[0]
        ser = per_call_us(lambda: inv.model_dump_json())[0]
        out.append(dict(lines=n, parse_us=parse, schema_us=v_schema, full_us=v_full, ser_us=ser))
        print(f"n={n:3d} parse={parse:7.1f} validate-schema={v_schema:7.1f} full={v_full:7.1f} serialize={ser:7.1f} µs")
    return out


CHILD = r"""
import sys, json, timeit, statistics
sys.path.insert(0, sys.argv[1])
from impls import _pydantic_v2_models
from payload import payload_bytes
m = _pydantic_v2_models("full"); raw = payload_bytes(12)
t = timeit.Timer(lambda: m.model_validate_json(raw)); n, _ = t.autorange()
xs = [x / n * 1e6 for x in t.repeat(11, n)]
print(json.dumps({"min": min(xs), "median": statistics.median(xs), "max": max(xs)}))
"""


def noise():
    rows = []
    for i in range(8):
        r = subprocess.run([sys.executable, "-c", CHILD, str(HERE)], capture_output=True, text=True, check=True)
        rows.append(json.loads(r.stdout))
        print(f"lần {i + 1}: min={rows[-1]['min']:.1f} trung vị={rows[-1]['median']:.1f} max={rows[-1]['max']:.1f} µs")
    return rows


def main():
    out = {"breakdown": breakdown(), "noise": noise()}
    (HERE / "results" / "breakdown.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
