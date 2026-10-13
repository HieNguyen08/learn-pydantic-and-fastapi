"""Lab 04 — ba cách viết cùng một endpoint chờ I/O 50 ms (Module 09).

Chạy server:  uvicorn app:app --port 8100 --loop uvloop --http httptools
"""
import asyncio
import time

from fastapi import FastAPI

app = FastAPI()
IO_S = 0.05


@app.get("/io/async")
async def io_async():
    await asyncio.sleep(IO_S)          # nhường event loop trong lúc chờ
    return {"ok": True}


@app.get("/io/sync")
def io_sync():
    time.sleep(IO_S)                   # chạy trong threadpool (mặc định 40 luồng)
    return {"ok": True}


@app.get("/io/blocking")
async def io_blocking():
    time.sleep(IO_S)                   # SAI: chặn event loop
    return {"ok": True}


@app.get("/health")
async def health():
    return {"ok": True}
