"""Chi phí của dependency injection trong FastAPI, đo trong tiến trình (Module 08).

So sánh dependency `async def`, `def` (chạy qua threadpool), dependency có `yield`,
và dependency dùng lại (cache) theo số lượng k.
Chạy:  python bench_deps.py → results/deps.json
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from bench_inside_fastapi import per_request_us  # noqa: E402


def chain_app(k: int, kind: str):
    """k dependency nối tiếp nhau (mỗi cái phụ thuộc cái trước)."""
    app = FastAPI()

    async def a0():
        return 0

    def s0():
        return 0

    async def y0():
        yield 0

    prev = {"async": a0, "sync": s0, "yield": y0, "cached": a0}[kind]
    for _ in range(k):
        def make(p):
            if kind in ("async", "cached"):
                async def d(x: Annotated[int, Depends(p)]):
                    return x + 1
            elif kind == "sync":
                def d(x: Annotated[int, Depends(p)]):
                    return x + 1
            else:
                async def d(x: Annotated[int, Depends(p)]):
                    yield x + 1
            return d
        prev = make(prev) if kind != "cached" else prev
    if kind == "cached":
        # k lần khai báo CÙNG một dependency → chỉ chạy một lần nhờ cache
        deps = [Depends(prev) for _ in range(k)]

        async def handler(**kw):
            return {"ok": True}
        import inspect
        handler.__signature__ = inspect.Signature([
            inspect.Parameter(f"d{i}", inspect.Parameter.KEYWORD_ONLY, annotation=Annotated[int, deps[i]])
            for i in range(k)])
    else:
        async def handler(x: Annotated[int, Depends(prev)]):
            return {"depth": x}
    app.add_api_route("/x", handler, methods=["GET"])
    return app


async def main():
    rows = []
    for kind in ("async", "sync", "yield", "cached"):
        for k in (0, 1, 5, 10, 20):
            us = await per_request_us(chain_app(k, kind), "GET", "/x", b"", n=1500)
            rows.append(dict(kind=kind, k=k, us=us))
            print(f"{kind:7s} k={k:2d} {us:7.1f} µs/request")
    (HERE / "results" / "deps.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
