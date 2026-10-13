"""Ứng dụng FastAPI dùng cho benchmark đồng thời (Module 08, 09).

Chạy:  uvicorn bench_app:app --port 8100 [--workers N]
Biến môi trường:
  IO_MS       thời gian "I/O giả lập" mỗi request (mặc định 50 ms)
  THREADS     số luồng tối đa của threadpool anyio (mặc định của anyio là 40)
"""
import asyncio
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import anyio.to_thread
from fastapi import Depends, FastAPI

sys.path.insert(0, str(Path(__file__).parent))
from impls import _pydantic_v2_models  # noqa: E402

IO_S = float(os.environ.get("IO_MS", "50")) / 1000

if os.environ.get("FORCE_NODELAY"):
    # Thí nghiệm Module 09: socket do uvicorn --workers tạo có proto=0 nên asyncio bỏ qua TCP_NODELAY.
    # Bản vá này bật TCP_NODELAY cho mọi socket TCP được accept để kiểm chứng nguyên nhân.
    import asyncio.base_events as _be
    import asyncio.selector_events as _se
    import socket as _socket

    def _force_nodelay(sock):
        if sock.family in (_socket.AF_INET, _socket.AF_INET6) and sock.type == _socket.SOCK_STREAM:
            sock.setsockopt(_socket.IPPROTO_TCP, _socket.TCP_NODELAY, 1)
    _be._set_nodelay = _force_nodelay
    _se._set_nodelay = _force_nodelay

Invoice = _pydantic_v2_models("full")


@asynccontextmanager
async def lifespan(app):
    threads = os.environ.get("THREADS")
    if threads:
        anyio.to_thread.current_default_thread_limiter().total_tokens = int(threads)
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/io/async")
async def io_async():
    await asyncio.sleep(IO_S)          # nhường event loop trong lúc chờ
    return {"mode": "async"}


@app.get("/io/sync")
def io_sync():
    time.sleep(IO_S)                   # chạy trong threadpool → không chặn loop
    return {"mode": "sync"}


@app.get("/io/blocking")
async def io_blocking():
    time.sleep(IO_S)                   # SAI: chặn cả event loop
    return {"mode": "blocking"}


def burn(ms: float):
    end = time.perf_counter() + ms / 1000
    x = 0
    while time.perf_counter() < end:
        x += 1
    return x


@app.get("/cpu/{ms}")
async def cpu(ms: float):
    burn(ms)
    return {"ms": ms}


@app.post("/invoices")
async def create_invoice(inv: Invoice):
    return {"number": inv.number, "total": inv.total, "lines": len(inv.lines)}


@app.post("/invoices/sync")
def create_invoice_sync(inv: Invoice):
    return {"number": inv.number, "total": inv.total, "lines": len(inv.lines)}


# ---- chuỗi dependency dài n (Module 08) -------------------------------------------
def make_chain(n: int):
    async def d0():
        return 0
    prev = d0
    for i in range(n):
        def make(p):
            async def dep(x: Annotated[int, Depends(p)]):
                return x + 1
            return dep
        prev = make(prev)
    return prev


for n in (0, 1, 5, 10, 20):
    dep = make_chain(n)

    async def handler(x: Annotated[int, Depends(dep)]):
        return {"depth": x}

    app.add_api_route(f"/deps/{n}", handler, methods=["GET"])


# ---- middleware (Module 07): MW_KIND=base|asgi, MW_K=số lớp -----------------------
def _add_middlewares():
    from starlette.middleware.base import BaseHTTPMiddleware

    kind, k = os.environ.get("MW_KIND"), int(os.environ.get("MW_K", "0"))

    async def passthrough(request, call_next):
        return await call_next(request)

    class PureASGI:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            await self.app(scope, receive, send)

    for _ in range(k):
        if kind == "base":
            app.add_middleware(BaseHTTPMiddleware, dispatch=passthrough)
        elif kind == "asgi":
            app.add_middleware(PureASGI)


_add_middlewares()
