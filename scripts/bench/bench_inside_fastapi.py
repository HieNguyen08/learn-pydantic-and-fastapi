"""Thời gian bên trong FastAPI cho một request, đo trong tiến trình (không có mạng, không có server) — Module 07.

Gọi thẳng app ASGI với receive/send giả để tách chi phí của framework khỏi chi phí của bộ phân tích HTTP.
  1. Chi phí theo biến thể endpoint (GET rỗng, POST hóa đơn, có/không response_model).
  2. Chi phí middleware: 0/1/5 lớp BaseHTTPMiddleware so với ASGI middleware thuần.
  3. Hồ sơ cProfile: thời gian tự thân (tottime) gom theo thư viện.
Chạy:  python bench_inside_fastapi.py → results/inside_fastapi.json
"""
import asyncio
import cProfile
import json
import pstats
import sys
import time
from pathlib import Path

from fastapi import FastAPI, Request
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from impls import _pydantic_v2_models  # noqa: E402
from payload import payload_bytes  # noqa: E402

Invoice = _pydantic_v2_models("full")
BODY = payload_bytes(12)


class Created(BaseModel):
    number: int
    total: int
    lines: int


def build_app(n_base_mw=0, n_asgi_mw=0):
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.post("/invoices")
    async def create(inv: Invoice):
        return {"number": inv.number, "total": inv.total, "lines": len(inv.lines)}

    @app.post("/invoices/typed")
    async def create_typed(inv: Invoice) -> Created:
        return Created(number=inv.number, total=inv.total, lines=len(inv.lines))

    @app.post("/invoices/echo")
    async def echo(inv: Invoice) -> Invoice:          # serialize lại cả hóa đơn
        return inv

    @app.post("/invoices/fast")
    async def create_fast(request: Request) -> Created:   # tự đọc byte, dùng đường JSON của Pydantic
        inv = Invoice.model_validate_json(await request.body())
        return Created(number=inv.number, total=inv.total, lines=len(inv.lines))

    async def passthrough(request, call_next):
        return await call_next(request)

    for _ in range(n_base_mw):
        app.add_middleware(BaseHTTPMiddleware, dispatch=passthrough)

    class PureASGI:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            await self.app(scope, receive, send)

    for _ in range(n_asgi_mw):
        app.add_middleware(PureASGI)
    return app


def scope_for(method, path, body):
    return {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "scheme": "http",
            "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "",
            "headers": [(b"host", b"x"), (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode())],
            "client": ("127.0.0.1", 1), "server": ("127.0.0.1", 80)}


async def call(app, method, path, body):
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        await asyncio.sleep(3600)

    status = None

    async def send(msg):
        nonlocal status
        if msg["type"] == "http.response.start":
            status = msg["status"]

    await app(scope_for(method, path, body), receive, send)
    return status


async def per_request_us(app, method, path, body, n=3000):
    for _ in range(200):
        assert await call(app, method, path, body) == 200
    best = float("inf")
    for _ in range(5):
        t0 = time.perf_counter()
        for _ in range(n):
            await call(app, method, path, body)
        best = min(best, (time.perf_counter() - t0) / n * 1e6)
    return best


def group(stats):
    buckets = {}
    for (file, _, func), (cc, nc, tt, ct, callers) in stats.stats.items():
        f = file.replace("\\", "/")
        if "/pydantic" in f or f.startswith("~") and "pydantic" in func:
            k = "Pydantic (Python + Rust)"
        elif "/fastapi/" in f:
            k = "FastAPI"
        elif "/starlette/" in f:
            k = "Starlette"
        elif "/anyio/" in f:
            k = "anyio"
        elif "/asyncio/" in f or "_asyncio" in func or "<built-in method _asyncio" in func:
            k = "asyncio"
        elif "bench_inside_fastapi" in f:
            k = "driver đo (không tính)"
        elif "impls.py" in f or "payload.py" in f:
            k = "code của bạn (handler, validator)"
        else:
            k = "khác (stdlib, json, typing…)"
        buckets[k] = buckets.get(k, 0) + tt
    return buckets


async def main():
    out = {"variants": [], "middleware": [], "profile": {}}
    app = build_app()
    for name, method, path, body in (("GET /health (dict)", "GET", "/health", b""),
                                     ("POST /invoices → dict", "POST", "/invoices", BODY),
                                     ("POST /invoices → response_model nhỏ", "POST", "/invoices/typed", BODY),
                                     ("POST /invoices → trả lại cả hóa đơn", "POST", "/invoices/echo", BODY),
                                     ("POST /invoices, tự model_validate_json", "POST", "/invoices/fast", BODY)):
        us = await per_request_us(app, method, path, body)
        out["variants"].append(dict(name=name, us=us))
        print(f"{name:40s} {us:7.1f} µs/request (trong tiến trình)")
    for kind in ("BaseHTTPMiddleware", "ASGI thuần"):
        for k in (0, 1, 5):
            a = build_app(n_base_mw=k if kind == "BaseHTTPMiddleware" else 0, n_asgi_mw=k if kind == "ASGI thuần" else 0)
            us = await per_request_us(a, "GET", "/health", b"", n=2000)
            out["middleware"].append(dict(kind=kind, layers=k, us=us))
            print(f"{kind:20s} {k} lớp  {us:7.1f} µs/request")
    prof = cProfile.Profile()
    prof.enable()
    for _ in range(3000):
        await call(app, "POST", "/invoices/typed", BODY)
    prof.disable()
    b = group(pstats.Stats(prof))
    b.pop("driver đo (không tính)", None)
    tot = sum(b.values())
    out["profile"] = {k: v / tot for k, v in sorted(b.items(), key=lambda kv: -kv[1])}
    for k, v in out["profile"].items():
        print(f"  {k:36s} {v * 100:5.1f}%")
    (HERE / "results" / "inside_fastapi.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
