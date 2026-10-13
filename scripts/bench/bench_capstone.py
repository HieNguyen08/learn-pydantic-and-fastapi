"""Thí nghiệm cho Module 14 (capstone): kiểm chứng ước lượng thiết kế bằng invoice-api thu gọn (capstone_app.py).

  c1  ngân sách latency của một POST /v1/invoices (12 dòng) — từng thành phần và toàn bộ, trong tiến trình
  c2  tải open-loop lên uvicorn thật (1 và 2 tiến trình; lớp DB SQLAlchemy và asyncpg thuần): thông lượng, p50/p99
  c3  CPU phía Python của cùng một transaction qua SQLAlchemy text() và asyncpg thuần
Yêu cầu: Postgres (PG_DSN) và Redis (REDIS_URL) như bench_db.py / bench_security.py; chạy `python capstone_app.py init`
trước (script tự gọi). Chạy:  python bench_capstone.py [--only c1]
"""
import argparse
import asyncio
import json
import os
import random
import socket
import statistics
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "results" / "capstone.json"
sys.path.insert(0, str(HERE))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p / 100 * (len(xs) - 1)))] if xs else None


# ---------------------------------------------------------------- c1
def c1_budget(res, n=600):
    import jwt
    import capstone_app as C
    from bench_inside_fastapi import scope_for
    from payload import payload_bytes
    toks = json.loads((C.KEYS / "tokens.json").read_text())
    body = payload_bytes(12)

    def best_us(fn, k=2000):
        fn()
        b = float("inf")
        for _ in range(5):
            t0 = time.perf_counter()
            for _ in range(k):
                fn()
            b = min(b, (time.perf_counter() - t0) / k * 1e6)
        return b

    rows = []
    rows.append(("kiểm JWT EdDSA + Principal", best_us(lambda: C.Principal.model_validate(jwt.decode(
        toks[0], C.PUBLIC_KEY, algorithms=["EdDSA"], audience="invoice-api", issuer="https://id.mekong.vn")))))
    rows.append(("validate InvoiceIn (12 dòng, model_validate_json)", best_us(
        lambda: C.InvoiceCreate.model_validate_json(body))))
    inv = C.InvoiceCreate.model_validate_json(body)
    rows.append(("băm model cho idempotency (model_dump_json + sha256)", best_us(
        lambda: __import__("hashlib").sha256(inv.model_dump_json().encode()).hexdigest())))

    async def async_parts():
        out = []
        lat = []
        for _ in range(n):
            t0 = time.perf_counter()
            await C.gcra(keys=["rl:bench"], args=[1 / 1e6, 1e6])
            lat.append((time.perf_counter() - t0) * 1e6)
        out.append(("GCRA trên Redis (1 round trip)", statistics.median(lat)))

        # transaction DB đầy đủ như trong handler (không qua HTTP), đo riêng
        from sqlalchemy import text
        lat = []
        for i in range(n):
            t0 = time.perf_counter()
            async with C.SessionLocal() as s, s.begin():
                await s.execute(text("select set_config('app.tenant_id', '1', true)"))
                await s.scalar(text("insert into cap_idempotency(tenant_id, key, request_hash) values (1, :k, 'h') "
                                    "on conflict do nothing returning key"), {"k": uuid.uuid4()})
                iid = await s.scalar(text(
                    "insert into cap_invoices (tenant_id, series, number, seller_tax_code, buyer_name, issued_at, "
                    "total_before_tax, total_tax, total) values (1, '1C26TMK', 0, 'x', 'b', now(), 1, 1, 2) returning id"))
                await s.execute(text(
                    "insert into cap_lines (invoice_id, tenant_id, line_no, name, quantity, unit_price, vat_rate, amount)"
                    " values (:i, 1, :n, 'x', 1, 1, '10', 1)"), [dict(i=iid, n=j) for j in range(1, 13)])
                num = await s.scalar(text("update cap_series set last_number = last_number + 1 where tenant_id = 1 "
                                          "and series = '1C26TMK' returning last_number"))
                await s.execute(text("update cap_invoices set number = :n where id = :i"), {"n": num, "i": iid})
                await s.execute(text("insert into cap_outbox (tenant_id, topic, payload) values (1, 't', '{}')"))
                await s.execute(text("update cap_idempotency set status_code = 201 where tenant_id = 1 and key = :k"),
                                {"k": uuid.uuid4()})
            lat.append((time.perf_counter() - t0) * 1e6)
        out.append(("transaction Postgres (8 câu lệnh, RLS, commit)", statistics.median(lat)))

        # toàn bộ request qua ASGI trong tiến trình
        lat = []
        for i in range(n):
            hdrs = [(b"host", b"x"), (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"authorization", f"Bearer {toks[i % len(toks)]}".encode()),
                    (b"idempotency-key", str(uuid.uuid4()).encode())]
            scope = scope_for("POST", "/v1/invoices", body)
            scope["headers"] = hdrs
            sent = False
            st = {}

            async def receive():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": body, "more_body": False}
                await asyncio.sleep(3600)

            async def send(m):
                if m["type"] == "http.response.start":
                    st["s"] = m["status"]
            t0 = time.perf_counter()
            await C.app(scope, receive, send)
            lat.append((time.perf_counter() - t0) * 1e6)
            assert st["s"] == 201, st
        out.append(("TOÀN BỘ POST /v1/invoices (trong tiến trình)", statistics.median(lat)))
        out.append(("TOÀN BỘ — p99", pct(lat, 99)))
        await C.engine.dispose()
        return out
    rows += asyncio.run(async_parts())
    res["c1_budget"] = [dict(part=k, us=v) for k, v in rows]
    for k, v in rows:
        print(f"c1 {k:55s} {v:9.1f} µs")


# ---------------------------------------------------------------- c2
async def open_loop(port, rate, duration, toks, body, timeout=2.0, seed=1, max_conns=1000):
    from loadgen import Conn
    rng = random.Random(seed)
    idle = []
    sem = asyncio.Semaphore(max_conns)
    out = dict(codes={}, timeout=0, error=0)
    lat = []
    tasks = []
    t_start = time.perf_counter()
    warm = t_start + 1.0

    def raw(i):
        head = (f"POST /v1/invoices HTTP/1.1\r\nHost: x\r\nConnection: keep-alive\r\n"
                f"Authorization: Bearer {toks[i % len(toks)]}\r\nIdempotency-Key: {uuid.uuid4()}\r\n"
                f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n")
        return head.encode() + body

    async def one(i, t_sched):
        async with sem:
            c = idle.pop() if idle else None
            try:
                if c is None:
                    c = Conn("127.0.0.1", port)
                    await c.open()
                try:
                    st = await asyncio.wait_for(c.request(raw(i)), max(0.001, t_sched + timeout - time.perf_counter()))
                except (ConnectionError, OSError, IndexError, ValueError):
                    c.close()
                    c = Conn("127.0.0.1", port)
                    await c.open()
                    st = await asyncio.wait_for(c.request(raw(i)), max(0.001, t_sched + timeout - time.perf_counter()))
                t1 = time.perf_counter()
                idle.append(c)
                if t_sched >= warm:
                    out["codes"][st] = out["codes"].get(st, 0) + 1
                    if st == 201:
                        lat.append((t1 - t_sched) * 1000)
            except asyncio.TimeoutError:
                if t_sched >= warm:
                    out["timeout"] += 1
                if c:
                    c.close()
            except (ConnectionError, OSError):
                if t_sched >= warm:
                    out["error"] += 1

    t = t_start
    i = 0
    while True:
        t += rng.expovariate(rate)
        if t >= t_start + 1.0 + duration:
            break
        now = time.perf_counter()
        if t > now:
            await asyncio.sleep(t - now)
        tasks.append(asyncio.create_task(one(i, t)))
        i += 1
    await asyncio.gather(*tasks)
    for c in idle:
        c.close()
    ok = out["codes"].get(201, 0)
    out.update(rate=rate, ok_per_s=ok / duration, p50=pct(lat, 50), p90=pct(lat, 90), p99=pct(lat, 99))
    return out


def c2_load(res):
    import capstone_app as C
    from payload import payload_bytes
    asyncio.run(C.init_db())
    toks = json.loads((C.KEYS / "tokens.json").read_text())
    body = payload_bytes(12)
    rows = []
    configs = (("sqlalchemy", 1, (100, 200, 300, 400)), ("asyncpg", 1, (100, 200, 300, 400, 500)),
               ("sqlalchemy", 2, (300, 500, 700)), ("asyncpg", 2, (400, 600, 800)))
    for layer, workers, rates in configs:
        for rate in rates:
            port = free_port()
            env = {**os.environ, "POOL": "8", "SHED": "64", "DB_LAYER": layer}
            args = [sys.executable, "-m", "uvicorn", "capstone_app:app", "--port", str(port), "--log-level", "warning",
                    "--loop", "uvloop", "--http", "httptools"]
            if workers > 1:
                args += ["--workers", str(workers)]
            proc = subprocess.Popen(args, cwd=HERE, env=env)
            try:
                for _ in range(200):
                    try:
                        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                        break
                    except OSError:
                        time.sleep(0.05)
                time.sleep(0.5 if workers == 1 else 1.5)
                pids = [proc.pid] + [int(x) for x in subprocess.run(["pgrep", "-P", str(proc.pid)], capture_output=True,
                                                                   text=True).stdout.split()]

                def cpu_s():
                    tot = 0
                    for pid in pids:
                        try:
                            f = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
                            tot += (int(f[11]) + int(f[12])) / os.sysconf("SC_CLK_TCK")
                        except FileNotFoundError:
                            pass
                    return tot
                c0 = cpu_s()
                r = asyncio.run(open_loop(port, rate, 8.0, toks, body))
                r["server_cpu_ms_per_req"] = (cpu_s() - c0) * 1000 / max(1, sum(r["codes"].values()))
            finally:
                proc.terminate()
                proc.wait()
            r["workers"] = workers
            r["layer"] = layer
            rows.append(r)
            print(f"c2 {layer:10s} {workers} tiến trình, tải {rate:4d}/s: 201 {r['ok_per_s']:6.1f}/s  p50 {r['p50']}  p99 {r['p99']}  "
                  f"CPU server {r['server_cpu_ms_per_req']:.2f} ms/req  "
                  f"mã {r['codes']} timeout {r['timeout']} lỗi {r['error']}")
    res["c2_load"] = rows


# ---------------------------------------------------------------- c3
def c3_db_layer_cpu(res, n=400):
    """Cùng một transaction POST (8 câu lệnh, 12 dòng): CPU phía Python qua SQLAlchemy text() và asyncpg thuần."""
    import asyncpg
    import capstone_app as C
    from sqlalchemy import text

    INS_LINE = ("insert into cap_lines (invoice_id, tenant_id, line_no, name, quantity, unit_price, vat_rate, amount) "
                "values ({i}, 1, {n}, 'x', 1, 1, '10', 1)")

    async def sa_full():
        async with C.SessionLocal() as s, s.begin():
            await s.execute(text("select set_config('app.tenant_id', '1', true)"))
            k = uuid.uuid4()
            await s.scalar(text("insert into cap_idempotency(tenant_id, key, request_hash) values (1, :k, 'h') "
                                "on conflict do nothing returning key"), {"k": k})
            iid = await s.scalar(text(
                "insert into cap_invoices (tenant_id, series, number, seller_tax_code, buyer_name, issued_at, "
                "total_before_tax, total_tax, total) values (1, '1C26TMK', 0, 'x', 'b', now(), 1, 1, 2) returning id"))
            await s.execute(text(INS_LINE.format(i=":i", n=":n")), [dict(i=iid, n=j) for j in range(1, 13)])
            num = await s.scalar(text("update cap_series set last_number = last_number + 1 where tenant_id = 1 "
                                      "and series = '1C26TMK' returning last_number"))
            await s.execute(text("update cap_invoices set number = :n where id = :i"), {"n": num, "i": iid})
            await s.execute(text("insert into cap_outbox (tenant_id, topic, payload) values (1, 't', '{}')"))
            await s.execute(text("update cap_idempotency set status_code = 201 where tenant_id = 1 and key = :k"), {"k": k})

    async def sa_lines():
        async with C.SessionLocal() as s, s.begin():
            await s.execute(text("select set_config('app.tenant_id', '1', true)"))
            await s.execute(text(INS_LINE.format(i="1", n=":n")), [dict(n=j) for j in range(1, 13)])

    async def sa_empty():
        async with C.SessionLocal() as s, s.begin():
            await s.execute(text("select set_config('app.tenant_id', '1', true)"))

    async def sa_selects():
        async with C.SessionLocal() as s, s.begin():
            for _ in range(8):
                await s.execute(text("select 1"))

    conn = await_conn = None

    async def run():
        nonlocal conn
        conn = await asyncpg.connect(host="/tmp", port=5433, user="app", database="bench")

        async def apg_full():
            async with conn.transaction():
                await conn.execute("select set_config('app.tenant_id', '1', true)")
                k = uuid.uuid4()
                await conn.fetchval("insert into cap_idempotency(tenant_id, key, request_hash) values (1, $1, 'h') "
                                    "on conflict do nothing returning key", k)
                iid = await conn.fetchval(
                    "insert into cap_invoices (tenant_id, series, number, seller_tax_code, buyer_name, issued_at, "
                    "total_before_tax, total_tax, total) values (1, '1C26TMK', 0, 'x', 'b', now(), 1, 1, 2) returning id")
                await conn.executemany(INS_LINE.format(i="$1", n="$2"), [(iid, j) for j in range(1, 13)])
                num = await conn.fetchval("update cap_series set last_number = last_number + 1 where tenant_id = 1 "
                                          "and series = '1C26TMK' returning last_number")
                await conn.execute("update cap_invoices set number = $1 where id = $2", num, iid)
                await conn.execute("insert into cap_outbox (tenant_id, topic, payload) values (1, 't', '{}')")
                await conn.execute("update cap_idempotency set status_code = 201 where tenant_id = 1 and key = $1", k)

        async def apg_selects():
            async with conn.transaction():
                for _ in range(8):
                    await conn.execute("select 1")
        rows = []
        for name, f in (("SQLAlchemy text(): transaction POST đầy đủ", sa_full),
                        ("asyncpg thuần: transaction POST đầy đủ", apg_full),
                        ("SQLAlchemy: chỉ executemany 12 dòng", sa_lines),
                        ("SQLAlchemy: transaction rỗng (begin + set_config + commit)", sa_empty),
                        ("SQLAlchemy: 8 × select 1", sa_selects),
                        ("asyncpg thuần: 8 × select 1", apg_selects)):
            for _ in range(30):
                await f()
            c0, w0 = time.process_time(), time.perf_counter()
            for _ in range(n):
                await f()
            rows.append(dict(case=name, cpu_ms=(time.process_time() - c0) * 1000 / n,
                             wall_ms=(time.perf_counter() - w0) * 1000 / n))
        await conn.close()
        await C.engine.dispose()
        return rows
    rows = asyncio.run(run())
    for r in rows:
        print(f"c3 {r['case']:58s} CPU {r['cpu_ms']:5.2f} ms   thời gian {r['wall_ms']:5.2f} ms")
    res["c3_db_layer_cpu"] = rows


EXPS = dict(c1=c1_budget, c2=c2_load, c3=c3_db_layer_cpu)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    if not (HERE / "results" / "_capstone_keys" / "tokens.json").exists():
        subprocess.run([sys.executable, "capstone_app.py", "init"], cwd=HERE, check=True)
    res = json.loads(OUT.read_text()) if OUT.exists() else {}
    for k, f in EXPS.items():
        if a.only and k not in a.only:
            continue
        f(res)
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
