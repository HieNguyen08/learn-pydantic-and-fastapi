"""Lab 03 — invoice-api hoàn chỉnh (thu gọn): DI, SQLite async, idempotency, JWT, chống BOLA.

Chạy:  uvicorn app.main:app --reload       rồi mở http://127.0.0.1:8000/docs
       python -m app.main token 1         in token thử cho tenant 1
"""
import hashlib
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Security
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

sys.path.insert(0, str(Path(__file__).parents[2] / "lab01_invoice_models"))
from invoice import Invoice  # noqa: E402  — model của Lab 01

from .db import Database, IdempotencyKey, InvoiceRow, LineRow, create_schema, make_engine  # noqa: E402
from .security import KeyPair, Principal, current_principal  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = getattr(app.state, "engine", None) or make_engine()
    await create_schema(engine)
    app.state.db = Database(engine)
    app.state.keys = getattr(app.state, "keys", None) or KeyPair()
    yield
    await engine.dispose()


app = FastAPI(title="invoice-api (Lab 03)", lifespan=lifespan)


async def db_session(request: Request):
    async for s in request.app.state.db.session():
        yield s


DB = Annotated[AsyncSession, Depends(db_session, scope="function")]       # commit TRƯỚC khi trả response
Writer = Annotated[Principal, Security(current_principal, scopes=["invoice:write"])]
Reader = Annotated[Principal, Security(current_principal, scopes=["invoice:read"])]


class LineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    unit_price: int
    vat_rate: str
    amount: int


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    series: str
    number: int
    buyer_name: str
    total: int
    lines: list[LineOut]


@app.post("/v1/invoices", status_code=201, response_model=InvoiceOut,
          responses={401: {}, 403: {}, 409: {}, 422: {}})
async def create_invoice(body: Invoice, db: DB, p: Writer, idempotency_key: Annotated[UUID, Header()]):
    req_hash = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    claimed = await db.scalar(text(
        "insert into idempotency_keys(tenant_id, key, request_hash) values (:t, :k, :h) "
        "on conflict (tenant_id, key) do nothing returning key"),
        {"t": p.tenant_id, "k": str(idempotency_key), "h": req_hash})
    if claimed is None:
        row = await db.get(IdempotencyKey, (p.tenant_id, str(idempotency_key)))
        if row.request_hash != req_hash:
            return JSONResponse({"title": "Idempotency-Key đã dùng cho payload khác"}, status_code=422)
        return JSONResponse(json.loads(row.response_body), status_code=row.status_code,
                            headers={"Idempotent-Replayed": "true"})
    inv = InvoiceRow(tenant_id=p.tenant_id, series="1C26TMK", number=None, seller_tax_code=body.seller_tax_code,
                     buyer_name=body.buyer.name, total_before_tax=body.total_before_tax,
                     total_tax=body.total_tax, total=body.total,
                     lines=[LineRow(name=l.name, quantity=l.quantity, unit_price=l.unit_price, vat_rate=l.vat_rate,
                                    amount=l.amount) for l in body.lines])
    db.add(inv)
    await db.flush()
    inv.number = await db.scalar(text(                                  # cấp số cuối transaction (Module 10)
        "update series set last_number = last_number + 1 where tenant_id = :t and series = '1C26TMK' "
        "returning last_number"), {"t": p.tenant_id})
    if inv.number is None:
        raise HTTPException(409, "tenant chưa đăng ký ký hiệu hóa đơn")
    out = InvoiceOut.model_validate(inv)
    key_row = await db.get(IdempotencyKey, (p.tenant_id, str(idempotency_key)))
    key_row.status_code, key_row.response_body = 201, out.model_dump_json()
    return out


@app.get("/v1/invoices/{invoice_id}", response_model=InvoiceOut, responses={404: {}})
async def get_invoice(invoice_id: int, db: DB, p: Reader):
    inv = await db.scalar(select(InvoiceRow).options(selectinload(InvoiceRow.lines))
                          .where(InvoiceRow.id == invoice_id, InvoiceRow.tenant_id == p.tenant_id))  # chống BOLA
    if inv is None:
        raise HTTPException(404, "không tìm thấy")
    return inv


if __name__ == "__main__" and sys.argv[1:2] == ["token"]:
    print("Khóa sinh ngẫu nhiên mỗi lần chạy server; dùng test hoặc /docs với token từ tests/conftest.py.")
