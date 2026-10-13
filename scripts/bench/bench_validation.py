"""Benchmark validation hóa đơn: nhiều thư viện × số dòng hàng × mức kiểm tra.

Chạy:  python bench_validation.py [--quick] [--out results/validation_<venv>.json]
Dùng chung cho venv Pydantic v2 và venv Pydantic v1 (thư viện nào không import được thì bỏ qua).
Kết quả: thời gian/lần (µs) = trung vị của R lần lặp, mỗi lần chạy đủ để ≥ 0,2 s.
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
import timeit
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from impls import IMPLS  # noqa: E402
from payload import make_invoice, payload_bytes  # noqa: E402

SIZES = (1, 12, 50, 200)


def measure(fn, arg, repeat):
    t = timeit.Timer(lambda: fn(arg))
    n, _ = t.autorange()
    n = max(n, 1)
    runs = [x / n for x in t.repeat(repeat=repeat, number=n)]
    return statistics.median(runs) * 1e6, (min(runs) * 1e6, max(runs) * 1e6)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    repeat = 3 if a.quick else 11
    res = {"python": sys.version.split()[0], "machine": platform.processor() or platform.machine(),
           "payload_bytes": {n: len(payload_bytes(n)) for n in SIZES}, "rows": []}
    try:
        import pydantic
        res["pydantic"] = pydantic.VERSION
    except Exception:
        pass
    for name, factory in IMPLS.items():
        if a.only and not any(o in name for o in a.only):
            continue
        for level in ("schema", "full"):
            if "chỉ parse" in name and level == "full":
                continue
            try:
                fn = factory(level)
            except ImportError:
                break
            except Exception as e:  # thư viện không có trong venv này
                if "pydantic v1" in name or "pydantic v2" in name:
                    break
                raise
            # kiểm tra đúng đắn: dữ liệu hợp lệ phải qua, dữ liệu sai tổng phải bị chặn ở mức full
            try:
                fn(payload_bytes(12))
            except Exception as e:
                print(f"SKIP {name}/{level}: {type(e).__name__}: {e}"[:200])
                break
            if level == "full":
                bad = make_invoice(12)
                bad["total"] += 1
                try:
                    fn(json.dumps(bad).encode())
                    raise SystemExit(f"{name} không bắt được lỗi tổng tiền!")
                except SystemExit:
                    raise
                except Exception:
                    pass
            for n in SIZES:
                raw = payload_bytes(n)
                med, (lo, hi) = measure(fn, raw, repeat)
                res["rows"].append(dict(impl=name, level=level, lines=n, us=med, lo=lo, hi=hi))
                print(f"{name:45s} {level:6s} lines={n:4d}  {med:10.1f} µs")
    # chi phí đường lỗi: payload sai kiểu ở 1 trường sâu (lines[5].quantity = "abc")
    out = Path(a.out or Path(__file__).parent / "results" / "validation.json")
    out.parent.mkdir(exist_ok=True, parents=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print("→", out)


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"xong trong {time.time() - t0:.0f}s")
