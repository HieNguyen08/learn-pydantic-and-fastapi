"""Đo RSS tăng thêm khi giữ n luồng đang ngủ so với n task asyncio đang chờ (Module 02).

Chạy:  python bench_threads_coroutines.py   → results/threads_coroutines.json
Mỗi phép đo chạy trong tiến trình con riêng để RSS không cộng dồn.
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent

CHILD = r'''
import asyncio, sys, threading, time, resource, os
def rss_mb():
    with open(f"/proc/{os.getpid()}/status") as f:
        for line in f:
            if line.startswith("VmRSS"):
                return int(line.split()[1]) / 1024
kind, n = sys.argv[1], int(sys.argv[2])
base = rss_mb()
t0 = time.perf_counter()
if kind == "thread":
    ev = threading.Event()
    ts = [threading.Thread(target=ev.wait) for _ in range(n)]
    for t in ts: t.start()
    created = time.perf_counter() - t0
    time.sleep(0.3)
    peak = rss_mb()
    ev.set()
    for t in ts: t.join()
else:
    async def main():
        ev = asyncio.Event()
        tasks = [asyncio.create_task(ev.wait()) for _ in range(n)]
        await asyncio.sleep(0)
        c = time.perf_counter() - t0
        await asyncio.sleep(0.3)
        p = rss_mb()
        ev.set()
        await asyncio.gather(*tasks)
        return c, p
    created, peak = asyncio.run(main())
print(peak - base, created)
'''


def main():
    rows = []
    for kind, ns in (("thread", (100, 500, 1000, 2000, 5000)), ("coroutine", (100, 1000, 5000, 10000, 50000, 100000))):
        for n in ns:
            out = subprocess.run([sys.executable, "-c", CHILD, kind, str(n)], capture_output=True, text=True, check=True).stdout
            mb, sec = map(float, out.split())
            rows.append(dict(kind=kind, n=n, rss_mb=mb, create_s=sec, kb_each=mb * 1024 / n))
            print(f"{kind:9s} n={n:6d} ΔRSS={mb:8.1f} MB  {mb*1024/n:6.1f} KB/cái  tạo {sec*1000:7.1f} ms")
    out = HERE / "results" / "threads_coroutines.json"
    out.write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
