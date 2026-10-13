"""Thí nghiệm cho Module 13 — Production & observability → results/production.json

  p1  graceful shutdown: SIGTERM khi đang có request 2 s; uvicorn mặc định vs --timeout-graceful-shutdown;
      request mới đến SAU SIGTERM
  p2  retry: mô phỏng backoff (không jitter / full / equal / decorrelated jitter) khi 100 client cùng thất bại
  p3  metastable failure: mô phỏng hàng đợi có timeout + retry; sự cố 10 s rồi hết — hệ thống có tự hồi phục?
  p4  percentile: trung bình p99 của các pod vs p99 thật; sai số histogram_quantile với bucket mặc định
  p5  chi phí quan sát: OTel native của FastAPI, log JSON, metric Prometheus — µs mỗi request (trong tiến trình)
  p6  load shedding: uvicorn --limit-concurrency dưới tải gấp đôi năng lực (open-loop, client timeout 1 s)
Chạy:  python bench_production.py [--only p2 p3]
"""
import argparse
import asyncio
import heapq
import json
import math
import os
import random
import signal
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "results" / "production.json"
sys.path.insert(0, str(HERE))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


APP_SRC = '''
import asyncio, os, time
from fastapi import FastAPI
app = FastAPI()

@app.get("/slow")
async def slow():
    await asyncio.sleep(2.0)
    return {"ok": True}

@app.get("/health")
async def health():
    return {"ok": True}

class InFlightLimit:
    """Load shedding ở tầng ứng dụng: đếm request ĐANG XỬ LÝ (không đếm kết nối rảnh); vượt ngưỡng → 503 ngay."""
    def __init__(self, app, limit):
        self.app, self.limit, self.inflight = app, limit, 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == "/health":
            return await self.app(scope, receive, send)
        if self.inflight >= self.limit:
            await send({"type": "http.response.start", "status": 503,
                        "headers": [(b"retry-after", b"1"), (b"content-length", b"0")]})
            return await send({"type": "http.response.body", "body": b""})
        self.inflight += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self.inflight -= 1

if os.environ.get("SHED"):
    app.add_middleware(InFlightLimit, limit=int(os.environ["SHED"]))

@app.get("/cpu")
def cpu():
    # ~CPU_MS ms CPU, chạy trong threadpool → mô phỏng request tốn CPU
    t = time.perf_counter() + float(os.environ.get("CPU_MS", "4")) / 1000
    x = 0
    while time.perf_counter() < t:
        x += 1
    return {"ok": True}
'''


def start(port, extra=(), env=None):
    (HERE / "_p_app.py").write_text(APP_SRC)
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", "_p_app:app", "--port", str(port), "--log-level",
                          "warning", *extra], cwd=HERE, env={**os.environ, **(env or {})})
    for _ in range(200):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return p
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("server không lên")


async def http_get(port, path, timeout=10.0):
    r, w = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), timeout)
    w.write(f"GET {path} HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n".encode())
    await w.drain()
    line = await asyncio.wait_for(r.readline(), timeout)
    w.close()
    if not line:
        raise ConnectionResetError("đóng kết nối không trả lời")
    return int(line.split()[1])


# ---------------------------------------------------------------- p1
def p1_graceful(res):
    rows = []
    for label, extra in (("uvicorn mặc định", ()), ("--timeout-graceful-shutdown 1", ("--timeout-graceful-shutdown", "1"))):
        port = free_port()
        proc = start(port, extra)

        async def scenario():
            results = {"inflight_ok": 0, "inflight_fail": 0, "after_ok": 0, "after_fail": 0}
            errs = []

            async def inflight():
                try:
                    st = await http_get(port, "/slow")
                    results["inflight_ok" if st == 200 else "inflight_fail"] += 1
                except Exception as e:  # noqa: BLE001
                    results["inflight_fail"] += 1
                    errs.append(type(e).__name__)

            async def after():
                await asyncio.sleep(0.8)              # request mới đến 0,3 s SAU SIGTERM
                try:
                    st = await http_get(port, "/health", timeout=3)
                    results["after_ok" if st == 200 else "after_fail"] += 1
                except Exception as e:  # noqa: BLE001
                    results["after_fail"] += 1
                    errs.append(type(e).__name__)

            tasks = [asyncio.create_task(inflight()) for _ in range(10)]
            tasks += [asyncio.create_task(after()) for _ in range(10)]
            await asyncio.sleep(0.5)
            t0 = time.perf_counter()
            proc.send_signal(signal.SIGTERM)
            await asyncio.gather(*tasks)
            while proc.poll() is None and time.perf_counter() - t0 < 10:
                await asyncio.sleep(0.02)
            results["exit_after_s"] = time.perf_counter() - t0
            results["errors"] = sorted(set(errs))
            return results
        r = asyncio.run(scenario())
        proc.wait()
        r["config"] = label
        rows.append(r)
        print(f"p1 {label:32s} đang chạy: {r['inflight_ok']} xong / {r['inflight_fail']} hỏng; "
              f"đến sau SIGTERM: {r['after_ok']} ok / {r['after_fail']} hỏng {r['errors']}; thoát sau {r['exit_after_s']:.2f} s")
    (HERE / "_p_app.py").unlink(missing_ok=True)
    res["p1_graceful"] = rows


# ---------------------------------------------------------------- p2
def p2_backoff(res, clients=100, seed=7):
    """Mô hình kiểu Brooker (AWS, 2015): tài nguyên dùng chung xử lý tối đa CAP lần gọi trong mỗi khe 10 ms;
    lần gọi vượt CAP thất bại (tranh chấp). 100 client cùng bắt đầu ở t=0, retry tới khi thành công."""
    CAP, SLOT, BASE, MAXB = 2, 0.010, 0.010, 2.0
    strategies = {
        "retry ngay (chờ 1 ms)": lambda n, prev, r: 0.001,
        "exponential, không jitter": lambda n, prev, r: min(MAXB, BASE * 2 ** n),
        "full jitter": lambda n, prev, r: r.uniform(0, min(MAXB, BASE * 2 ** n)),
        "equal jitter": lambda n, prev, r: (lambda v: v / 2 + r.uniform(0, v / 2))(min(MAXB, BASE * 2 ** n)),
        "decorrelated jitter": lambda n, prev, r: min(MAXB, r.uniform(BASE, prev * 3)),
    }
    rows = []
    for name, f in strategies.items():
        r = random.Random(seed)
        events = [(0.0, i, 0, BASE) for i in range(clients)]    # (thời điểm, client, số lần đã thử, sleep trước)
        heapq.heapify(events)
        slot_count = {}
        calls, done_at = 0, {}
        while events:
            t, c, n, prev = heapq.heappop(events)
            calls += 1
            slot = int(t // SLOT)
            slot_count[slot] = slot_count.get(slot, 0) + 1
            if slot_count[slot] <= CAP:
                done_at[c] = t
                continue
            if calls > 2_000_000:
                break
            sleep = f(n, prev, r)
            heapq.heappush(events, (t + sleep, c, n + 1, max(sleep, BASE)))
        ts = sorted(done_at.values())
        rows.append(dict(strategy=name, calls=calls, completed=len(ts), p50_s=ts[len(ts) // 2], all_done_s=ts[-1],
                         calls_per_client=calls / clients))
        print(f"p2 {name:28s} {calls:7d} lần gọi ({calls / clients:6.1f}/client), xong hết sau {ts[-1]:6.2f} s,"
              f" một nửa xong sau {ts[len(ts) // 2]:5.2f} s")
    res["p2_backoff"] = dict(clients=clients, cap_per_10ms=CAP, rows=rows)


# ---------------------------------------------------------------- p3
def simulate_metastable(policy, seed=3, T=120.0, lam=80.0, mu=100.0, trigger=(30.0, 40.0), mu_trigger=40.0,
                        timeout=1.0, max_retries=3):
    """Một server FIFO, năng lực mu req/s (giảm còn mu_trigger trong cửa sổ trigger), khách đến Poisson lam.
    Client hết chờ sau `timeout` s; server KHÔNG biết và vẫn xử lý request đã bị bỏ (công vô ích).
    policy: none | retry | retry_backoff_budget | shed
    Trả về goodput (request thành công ĐÚNG HẠN mỗi giây) theo từng giây."""
    rng = random.Random(seed)
    events = []                   # (time, kind, data)
    t = 0.0
    while t < T:
        t += rng.expovariate(lam)
        heapq.heappush(events, (t, 0, ("arrive", t, 0)))
    queue = []                    # [(t_enqueue, t_first, attempt)]
    busy_until = 0.0
    good = [0] * int(T + 1)
    offered = [0] * int(T + 1)
    retry_tokens = 0.0            # retry budget: tối đa 10% số request gốc
    import collections
    q = collections.deque()

    def rate_at(x):
        return mu_trigger if trigger[0] <= x < trigger[1] else mu

    seq = 1
    while events:
        now, _, ev = heapq.heappop(events)
        if now > T:
            break
        kind = ev[0]
        if kind == "arrive":
            _, t_first, attempt = ev
            offered[int(now)] += 1
            if attempt == 0:
                retry_tokens = min(retry_tokens + 0.1, 50)
            if policy == "shed" and len(q) / rate_at(now) > timeout:   # chờ dự kiến > timeout → từ chối ngay
                continue
            q.append((now, t_first, attempt))
            if busy_until <= now and len(q) == 1:
                heapq.heappush(events, (now, seq, ("serve",)))
                seq += 1
            # client đặt hẹn giờ timeout
            heapq.heappush(events, (now + timeout, seq, ("timeout", now, t_first, attempt)))
            seq += 1
        elif kind == "serve":
            if not q or busy_until > now + 1e-12:
                continue
            t_enq, t_first, attempt = q.popleft()
            svc = rng.expovariate(rate_at(now))
            busy_until = now + svc
            done = busy_until
            if done - t_enq <= timeout:
                good[int(min(done, T))] += 1
            heapq.heappush(events, (done, seq, ("serve",)))
            seq += 1
        elif kind == "timeout":
            _, t_enq, t_first, attempt = ev
            # nếu request này vẫn còn trong hàng đợi hoặc hoàn thành trễ → client bỏ và (có thể) retry
            finished_in_time = False
            # xấp xỉ: coi request hoàn thành đúng hạn nếu nó đã rời hàng đợi và được phục vụ trước t_enq+timeout
            still_waiting = any(x[0] == t_enq for x in q) if len(q) < 5000 else True
            if not still_waiting:
                finished_in_time = True
            if finished_in_time:
                continue
            if policy == "retry" and attempt < max_retries:
                heapq.heappush(events, (now, seq, ("arrive", t_first, attempt + 1)))
                seq += 1
            elif policy == "retry_backoff_budget" and attempt < max_retries and retry_tokens >= 1:
                retry_tokens -= 1
                backoff = rng.uniform(0, min(8.0, 0.5 * 2 ** attempt))
                heapq.heappush(events, (now + backoff, seq, ("arrive", t_first, attempt + 1)))
                seq += 1
    return good[: int(T)], offered[: int(T)]


def p3_metastable(res):
    out = {}
    for policy in ("none", "retry", "retry_backoff_budget", "shed"):
        good, offered = simulate_metastable(policy)
        out[policy] = dict(goodput=good, offered=offered,
                           before=statistics.fmean(good[10:30]), during=statistics.fmean(good[30:40]),
                           after=statistics.fmean(good[80:120]))
        print(f"p3 {policy:22s} goodput trước {out[policy]['before']:5.1f}/s, trong sự cố {out[policy]['during']:5.1f}/s,"
              f" 40 s sau khi hết sự cố {out[policy]['after']:5.1f}/s; tải gửi tới sau sự cố "
              f"{statistics.fmean(offered[80:120]):6.1f}/s")
    res["p3_metastable"] = out


# ---------------------------------------------------------------- p4
def p4_percentiles(res, seed=11):
    rng = random.Random(seed)
    # 4 pod: 3 pod khỏe, 1 pod "nóng" (hàng xóm ồn, GC) — latency lognormal (ms)
    pods = {"pod-a": (math.log(40), 0.35, 30000), "pod-b": (math.log(42), 0.35, 30000),
            "pod-c": (math.log(41), 0.35, 30000), "pod-d": (math.log(90), 0.6, 10000)}
    samples = {k: [rng.lognormvariate(m, s) for _ in range(n)] for k, (m, s, n) in pods.items()}

    def q(xs, p):
        xs = sorted(xs)
        return xs[int(p * (len(xs) - 1))]
    allx = [x for v in samples.values() for x in v]
    per_pod = {k: q(v, 0.99) for k, v in samples.items()}
    avg_p99 = statistics.fmean(per_pod.values())
    true_p99 = q(allx, 0.99)
    # histogram_quantile của Prometheus: nội suy tuyến tính trong bucket
    default_buckets = [5, 10, 25, 50, 75, 100, 250, 500, 750, 1000, 2500, 5000, 7500, 10000]
    tuned_buckets = [10, 20, 30, 40, 50, 60, 80, 100, 125, 150, 175, 200, 250, 300, 400, 500, 1000]

    def hist_q(xs, buckets, p):
        counts = [sum(1 for x in xs if x <= b) for b in buckets]
        total = len(xs)
        rank = p * total
        prev_b, prev_c = 0.0, 0
        for b, c in zip(buckets, counts):
            if c >= rank:
                return prev_b + (b - prev_b) * (rank - prev_c) / (c - prev_c)
            prev_b, prev_c = b, c
        return buckets[-1]
    out = dict(per_pod_p99=per_pod, avg_of_p99=avg_p99, true_p99=true_p99,
               hist_default=hist_q(allx, default_buckets, 0.99), hist_tuned=hist_q(allx, tuned_buckets, 0.99),
               true_p50=q(allx, 0.5), hist_default_p50=hist_q(allx, default_buckets, 0.5),
               samples_hist={k: [round(x, 1) for x in v[:2500]] for k, v in samples.items()})
    print(f"p4 p99 từng pod: { {k: round(v) for k, v in per_pod.items()} }")
    print(f"p4 trung bình các p99 = {avg_p99:.0f} ms; p99 thật (gộp mẫu) = {true_p99:.0f} ms; "
          f"histogram_quantile bucket mặc định = {out['hist_default']:.0f} ms; bucket chỉnh theo SLO = {out['hist_tuned']:.0f} ms")
    print(f"p4 p50 thật = {out['true_p50']:.1f} ms; histogram_quantile bucket mặc định = {out['hist_default_p50']:.1f} ms")
    res["p4_percentiles"] = out


# ---------------------------------------------------------------- p5
def p5_observability(res):
    import logging
    from bench_inside_fastapi import per_request_us
    from fastapi import FastAPI, Request
    from pydantic import BaseModel

    class Line(BaseModel):
        name: str
        amount: int

    class Inv(BaseModel):
        buyer: str
        lines: list[Line]
    body = json.dumps({"buyer": "Cty A", "lines": [{"name": f"Hàng {i}", "amount": 1000 * i} for i in range(12)]}).encode()

    def make(**kw):
        app = FastAPI(**kw)

        @app.post("/v1/invoices")
        async def create(inv: Inv):
            return {"total": sum(l.amount for l in inv.lines)}
        return app

    rows = []

    def measure(label, app):
        us = min(asyncio.run(per_request_us(app, "POST", "/v1/invoices", body, n=2000)) for _ in range(3))
        rows.append(dict(config=label, us=us))
        print(f"p5 {label:58s} {us:7.1f} µs/request")

    measure("không quan sát gì", make())

    # log JSON một dòng mỗi request (stdlib logging + formatter JSON tự viết), ghi vào /dev/null
    class JsonFmt(logging.Formatter):
        def format(self, r):
            return json.dumps({"ts": r.created, "lvl": r.levelname, "msg": r.getMessage(), **getattr(r, "ctx", {})})
    log = logging.getLogger("access")
    h = logging.FileHandler(os.devnull)
    h.setFormatter(JsonFmt())
    log.addHandler(h)
    log.setLevel(logging.INFO)
    log.propagate = False

    class AccessLog:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                return await self.app(scope, receive, send)
            t0 = time.perf_counter()
            status = {}

            async def s(m):
                if m["type"] == "http.response.start":
                    status["code"] = m["status"]
                await send(m)
            await self.app(scope, receive, s)
            log.info("request", extra={"ctx": {"path": scope["path"], "status": status.get("code"),
                                                "ms": round((time.perf_counter() - t0) * 1000, 3),
                                                "request_id": "8c1d…", "tenant": 7}})
    app2 = make()
    app2.add_middleware(AccessLog)
    measure("+ log JSON 1 dòng/request (ASGI middleware, stdlib logging)", app2)

    from prometheus_client import CollectorRegistry, Histogram
    reg = CollectorRegistry()
    hist = Histogram("http_request_duration_seconds", "x", ["route", "method", "status"], registry=reg)

    class Metrics:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                return await self.app(scope, receive, send)
            t0 = time.perf_counter()
            st = {}

            async def s(m):
                if m["type"] == "http.response.start":
                    st["c"] = m["status"]
                await send(m)
            await self.app(scope, receive, s)
            hist.labels("/v1/invoices", scope["method"], str(st.get("c"))).observe(time.perf_counter() - t0)
    app3 = make()
    app3.add_middleware(Metrics)
    measure("+ histogram Prometheus (ASGI middleware)", app3)

    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult

    class NullExporter(SpanExporter):
        def __init__(self):
            self.n = 0

        def export(self, spans):
            self.n += len(spans)
            return SpanExportResult.SUCCESS

    exp = NullExporter()
    tp = TracerProvider()
    tp.add_span_processor(BatchSpanProcessor(exp, max_queue_size=100_000))
    measure("+ OTel native của FastAPI: tracing, operation_spans=False",
            make(telemetry={"tracer_provider": tp, "metrics": False, "logs": False, "operation_spans": False}))
    measure("+ OTel native của FastAPI: tracing + operation_spans (mặc định)",
            make(telemetry={"tracer_provider": tp, "metrics": False, "logs": False}))
    from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
    tp10 = TracerProvider(sampler=TraceIdRatioBased(0.1))
    tp10.add_span_processor(BatchSpanProcessor(exp, max_queue_size=100_000))
    measure("+ OTel native, operation_spans, lấy mẫu 10%",
            make(telemetry={"tracer_provider": tp10, "metrics": False, "logs": False}))
    tp.force_flush()
    res["p5_observability"] = dict(rows=rows, spans_exported=exp.n)
    print(f"p5 số span đã xuất: {exp.n}")


# ---------------------------------------------------------------- p6
async def open_loop_timeout(port, path, rate, duration, timeout, seed=1, max_conns=2000):
    from loadgen import Conn, build_request
    host, p, raw = build_request(f"http://127.0.0.1:{port}{path}")
    rng = random.Random(seed)
    idle = []
    sem = asyncio.Semaphore(max_conns)
    out = dict(ok=0, shed=0, timeout=0, error=0, lat=[])
    tasks = []
    t_start = time.perf_counter()

    async def one(t_sched):
        async with sem:
            c = idle.pop() if idle else None
            try:
                if c is None:
                    c = Conn(host, p)
                    await asyncio.wait_for(c.open(), timeout)
                try:
                    st = await asyncio.wait_for(c.request(raw), max(0.001, t_sched + timeout - time.perf_counter()))
                except (ConnectionError, OSError, IndexError, ValueError):
                    # kết nối tái dùng đã bị server đóng (vd: sau 503) → mở lại, gửi lại một lần
                    c.close()
                    c = Conn(host, p)
                    await asyncio.wait_for(c.open(), timeout)
                    st = await asyncio.wait_for(c.request(raw), max(0.001, t_sched + timeout - time.perf_counter()))
                t1 = time.perf_counter()
                if st == 200:
                    out["ok"] += 1
                    out["lat"].append((t1 - t_sched) * 1000)
                elif st == 503:
                    out["shed"] += 1
                else:
                    out["error"] += 1
                idle.append(c)
            except asyncio.TimeoutError:
                out["timeout"] += 1
                if c:
                    c.close()
            except (ConnectionError, OSError, ValueError, IndexError):
                out["error"] += 1
                if c:
                    c.close()

    t = t_start
    while True:
        t += rng.expovariate(rate)
        if t >= t_start + duration:
            break
        now = time.perf_counter()
        if t > now:
            await asyncio.sleep(t - now)
        tasks.append(asyncio.create_task(one(t)))
    await asyncio.gather(*tasks)
    for c in idle:
        c.close()
    lat = sorted(out.pop("lat"))
    out.update(goodput=out["ok"] / duration, p50=lat[len(lat) // 2] if lat else None,
               p99=lat[int(len(lat) * .99)] if lat else None, sent=len(tasks))
    return out


def p6_load_shedding(res):
    rows = []
    cpu_ms = 4.0
    configs = (("không giới hạn", (), {}),
               ("uvicorn --limit-concurrency 20", ("--limit-concurrency", "20"), {}),
               ("ASGI middleware: tối đa 20 request in-flight", (), {"SHED": "20"}))
    for label, extra, env in configs:
        for rate in (150, 300):
            port = free_port()
            proc = start(port, ("--loop", "uvloop", "--http", "httptools", *extra), env={"CPU_MS": str(cpu_ms), **env})
            try:
                r = asyncio.run(open_loop_timeout(port, "/cpu", rate, 20.0, timeout=1.0))
            finally:
                proc.terminate()
                proc.wait()
            r.update(config=label, rate=rate)
            rows.append(r)
            print(f"p6 {label:44s} tải {rate:4d}/s: goodput {r['goodput']:6.1f}/s, ok {r['ok']}, 503 {r['shed']}, "
                  f"timeout {r['timeout']}, lỗi {r['error']}, p50 {r['p50']}, p99 {r['p99']}")
    (HERE / "_p_app.py").unlink(missing_ok=True)
    res["p6_load_shedding"] = dict(cpu_ms=cpu_ms, rows=rows)


EXPS = dict(p1=p1_graceful, p2=p2_backoff, p3=p3_metastable, p4=p4_percentiles, p5=p5_observability,
            p6=p6_load_shedding)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    res = json.loads(OUT.read_text()) if OUT.exists() else {}
    for k, f in EXPS.items():
        if a.only and k not in a.only:
            continue
        f(res)
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
