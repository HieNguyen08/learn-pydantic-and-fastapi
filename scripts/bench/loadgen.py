"""Bộ sinh tải HTTP/1.1 tối giản (asyncio thuần, keep-alive) để đo FastAPI.

Hai chế độ:
  closed-loop:  C kết nối, mỗi kết nối gửi request kế tiếp ngay khi nhận xong response.
                → đo throughput tối đa và latency ở mức đồng thời C.
  open-loop:    request đến theo quá trình Poisson tốc độ λ, độc lập với server.
                Latency tính từ THỜI ĐIỂM DỰ KIẾN gửi (tránh "coordinated omission").

Dùng như thư viện (run_closed / run_open) hoặc CLI:
  python loadgen.py closed http://127.0.0.1:8100/io/async -c 40 -d 4
  python loadgen.py open   http://127.0.0.1:8100/cpu/2   -r 300 -d 6
"""
import argparse
import asyncio
import json
import random
import time
from urllib.parse import urlsplit


def pct(xs, p):
    if not xs:
        return float("nan")
    xs = sorted(xs)
    k = min(len(xs) - 1, max(0, int(round(p / 100 * (len(xs) - 1)))))
    return xs[k]


class Conn:
    def __init__(self, host, port):
        self.host, self.port = host, port
        self.r = self.w = None

    async def open(self):
        self.r, self.w = await asyncio.open_connection(self.host, self.port)

    async def request(self, raw: bytes) -> int:
        self.w.write(raw)
        await self.w.drain()
        status_line = await self.r.readline()
        if not status_line:
            raise ConnectionResetError("server đã đóng kết nối (keep-alive timeout)")
        status = int(status_line.split()[1])
        length = 0
        while True:
            line = await self.r.readline()
            if line in (b"\r\n", b""):
                break
            k, _, v = line.partition(b":")
            if k.strip().lower() == b"content-length":
                length = int(v)
        if length:
            await self.r.readexactly(length)
        return status

    def close(self):
        if self.w:
            self.w.close()


def build_request(url: str, body: bytes | None = None) -> tuple[str, int, bytes]:
    u = urlsplit(url)
    path = u.path + (("?" + u.query) if u.query else "")
    method = "POST" if body is not None else "GET"
    head = f"{method} {path} HTTP/1.1\r\nHost: {u.hostname}\r\nConnection: keep-alive\r\n"
    if body is not None:
        head += f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n"
    raw = (head + "\r\n").encode() + (body or b"")
    return u.hostname, u.port or 80, raw


async def run_closed(url, concurrency, duration, warmup=1.0, body=None):
    host, port, raw = build_request(url, body)
    lat, errors = [], 0
    t_start = time.perf_counter()
    t_measure = t_start + warmup
    t_end = t_measure + duration

    async def worker():
        nonlocal errors
        c = Conn(host, port)
        await c.open()
        try:
            while True:
                t0 = time.perf_counter()
                if t0 >= t_end:
                    break
                st = await c.request(raw)
                t1 = time.perf_counter()
                if t0 >= t_measure:
                    if st >= 400:
                        errors += 1
                    lat.append(t1 - t0)
        finally:
            c.close()

    await asyncio.gather(*(worker() for _ in range(concurrency)))
    return summarize(lat, errors, duration, mode="closed", concurrency=concurrency)


async def run_open(url, rate, duration, warmup=1.0, body=None, max_conns=512, seed=1):
    """Poisson open-loop. Kết nối rảnh được tái dùng; thiếu thì mở thêm (tối đa max_conns)."""
    host, port, raw = build_request(url, body)
    rng = random.Random(seed)
    idle: list[Conn] = []
    nconn = 0
    sem = asyncio.Semaphore(max_conns)
    lat, errors = [], 0
    t_start = time.perf_counter()
    t_measure = t_start + warmup
    t_end = t_measure + duration
    tasks = []

    async def one(t_sched):
        nonlocal nconn, errors
        async with sem:
            c = idle.pop() if idle else None
            if c is None:
                c = Conn(host, port)
                await c.open()
                nconn += 1
            try:
                st = await c.request(raw)
            except (ConnectionError, OSError):
                # kết nối rảnh quá lâu đã bị server đóng → mở lại và gửi lại một lần
                c.close()
                c = Conn(host, port)
                await c.open()
                st = await c.request(raw)
            t1 = time.perf_counter()
            idle.append(c)
        if t_sched >= t_measure:
            if st >= 400:
                errors += 1
            lat.append(t1 - t_sched)  # tính từ lúc LẼ RA phải gửi

    t = t_start
    while True:
        t += rng.expovariate(rate)
        if t >= t_end:
            break
        now = time.perf_counter()
        if t > now:
            await asyncio.sleep(t - now)
        tasks.append(asyncio.create_task(one(t)))
    await asyncio.gather(*tasks)
    for c in idle:
        c.close()
    s = summarize(lat, errors, duration, mode="open", rate=rate)
    s["connections"] = nconn
    return s


def summarize(lat, errors, duration, **kw):
    ms = [x * 1000 for x in lat]
    return dict(kw, n=len(ms), errors=errors, rps=len(ms) / duration,
                p50=pct(ms, 50), p90=pct(ms, 90), p99=pct(ms, 99), max=max(ms) if ms else float("nan"),
                mean=sum(ms) / len(ms) if ms else float("nan"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["closed", "open"])
    ap.add_argument("url")
    ap.add_argument("-c", type=int, default=10)
    ap.add_argument("-r", type=float, default=100)
    ap.add_argument("-d", type=float, default=4)
    ap.add_argument("--body", default=None, help="file JSON để POST")
    a = ap.parse_args()
    body = open(a.body, "rb").read() if a.body else None
    if a.mode == "closed":
        res = asyncio.run(run_closed(a.url, a.c, a.d, body=body))
    else:
        res = asyncio.run(run_open(a.url, a.r, a.d, body=body))
    print(json.dumps(res))


if __name__ == "__main__":
    main()
