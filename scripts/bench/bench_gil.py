"""GIL: cùng tổng khối lượng CPU chia cho 1/2/4 luồng vs 1/2/4 tiến trình (Module 02).

Chạy:  python bench_gil.py → results/gil.json
"""
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
TOTAL = 8_000_000


def work(n):
    x = 0
    for i in range(n):
        x += i * i % 7
    return x


def run(pool_cls, k):
    with pool_cls(max_workers=k) as ex:
        list(ex.map(work, [10] * k))  # khởi động trước
        t0 = time.perf_counter()
        list(ex.map(work, [TOTAL // k] * k))
        return time.perf_counter() - t0


def main():
    gil = getattr(sys, "_is_gil_enabled", lambda: True)()
    rows = []
    for k in (1, 2, 4):
        for name, cls in (("luồng", ThreadPoolExecutor), ("tiến trình", ProcessPoolExecutor)):
            s = min(run(cls, k) for _ in range(3))
            rows.append(dict(kind=name, workers=k, seconds=s, gil=gil))
            print(f"{name:10s} k={k}  {s:.2f}s")
    (HERE / "results" / "gil.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
