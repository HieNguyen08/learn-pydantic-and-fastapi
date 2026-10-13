"""Lab 04 — bộ sinh tải closed-loop tối giản (asyncio thuần, keep-alive), dựa trên scripts/bench/loadgen.py.

Chạy:  python load.py http://127.0.0.1:8100/io/async -c 50 -d 4
       python load.py --sweep              (tự khởi động server, đo cả ba endpoint ở nhiều mức C)
"""
import argparse
import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts" / "bench"))
from loadgen import run_closed  # noqa: E402


def predict(path: str, c: int, io=0.05, threads=40) -> float:
    """Định luật Little: X = N / W — trần thông lượng lý thuyết."""
    if path.endswith("async"):
        return c / io
    if path.endswith("sync"):
        return min(c, threads) / io
    return 1 / io                                                       # blocking: 1 request tại một thời điểm


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def sweep():
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--port", str(port), "--log-level", "warning",
                             "--loop", "uvloop", "--http", "httptools"], cwd=Path(__file__).parent)
    try:
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.05)
        print(f"{'endpoint':14s} {'C':>4s} {'đo req/s':>9s} {'Little':>8s} {'p50 ms':>7s} {'p99 ms':>7s}")
        for path in ("/io/async", "/io/sync", "/io/blocking"):
            for c in (1, 10, 50, 100):
                r = asyncio.run(run_closed(f"http://127.0.0.1:{port}{path}", c, 3.0, warmup=0.5))
                print(f"{path:14s} {c:4d} {r['rps']:9.1f} {predict(path, c):8.0f} {r['p50']:7.1f} {r['p99']:7.1f}")
    finally:
        proc.terminate()
        proc.wait()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?")
    ap.add_argument("-c", type=int, default=50)
    ap.add_argument("-d", type=float, default=4.0)
    ap.add_argument("--sweep", action="store_true")
    a = ap.parse_args()
    if a.sweep or not a.url:
        sweep()
    else:
        r = asyncio.run(run_closed(a.url, a.c, a.d))
        print(r)
