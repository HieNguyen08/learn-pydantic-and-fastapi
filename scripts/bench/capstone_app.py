"""invoice-api thu gọn cho Module 14: ghép đủ các mảnh của Module 03–13 trên một đường POST.

  JWT EdDSA (M11) → GCRA theo tenant trên Redis (M11) → đọc body thô + model_validate_json (M06)
  → transaction Postgres: SET LOCAL tenant + RLS (M10) → idempotency ON CONFLICT (M10)
  → ghi hóa đơn 12 dòng → cấp số bằng khóa hàng, cuối transaction (M10) → outbox (M10)
  → lưu response cho idempotency → COMMIT trước 201 (M08) → response_model lọc trường (M07)
  + load shedding in-flight (M13)

Biến môi trường: PG_DSN_APP (role `app`, không sở hữu bảng), REDIS_URL, KEYS_DIR (khóa JWT), SHED.
Khởi tạo schema: python capstone_app.py init
"""
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Annotated, AsyncIterator
from uuid import UUID

import jwt
import redis.asyncio as aredis
from cryptography.hazmat.primitives import serialization
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Security, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, SecurityScopes
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent))
from invoice_v2 import InvoiceIn  # noqa: E402

HERE = Path(__file__).parent
KEYS = Path(os.environ.get("KEYS_DIR", HERE / "results" / "_capstone_keys"))
PG_DSN_APP = os.environ.get("PG_DSN_APP", "postgresql+asyncpg://app@/bench?host=/tmp&port=5433")
PG_DSN_ADMIN = os.environ.get("PG_DSN", "postgresql+asyncpg://postgres@/bench?host=/tmp&port=5433")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6390")

SCHEMA = """
drop table if exists cap_outbox, cap_idempotency, cap_lines, cap_invoices, cap_series cascade;
create table cap_series (tenant_id int not null, series text not null, last_number int not null default 0,
                         primary key (tenant_id, series));
create table cap_invoices (
  id bigserial primary key, tenant_id int not null, series text not null, number int not null,
  seller_tax_code text not null, buyer_name text not null, issued_at timestamptz not null,
  total_before_tax bigint not null, total_tax bigint not null, total bigint not null,
  created_at timestamptz not null default now(), unique (tenant_id, series, number));
create table cap_lines (
  id bigserial primary key, invoice_id bigint not null references cap_invoices(id), tenant_id int not null,
  line_no int not null, name text not null, quantity numeric(19,4) not null, unit_price bigint not null,
  vat_rate text not null, amount bigint not null);
create index on cap_lines (invoice_id);
create table cap_idempotency (
  tenant_id int not null, key uuid not null, request_hash text not null, status_code int, response_body jsonb,
  created_at timestamptz not null default now(), primary key (tenant_id, key));
create table cap_outbox (id bigserial primary key, tenant_id int not null, topic text not null, payload jsonb not null,
                         published_at timestamptz);
"""
RLS_TABLES = ("cap_series", "cap_invoices", "cap_lines", "cap_idempotency", "cap_outbox")


async def init_db(n_tenants=50):
    eng = create_async_engine(PG_DSN_ADMIN, isolation_level="AUTOCOMMIT")
    async with eng.connect() as c:
        if not await c.scalar(text("select 1 from pg_roles where rolname='app'")):
            await c.execute(text("create role app login"))
        for stmt in SCHEMA.split(";"):
            if stmt.strip():
                await c.execute(text(stmt))
        for t in RLS_TABLES:
            await c.execute(text(f"alter table {t} enable row level security"))
            await c.execute(text(f"alter table {t} force row level security"))
            await c.execute(text(f"create policy tenant_isolation on {t} using "
                                 f"(tenant_id = current_setting('app.tenant_id')::int) "
                                 f"with check (tenant_id = current_setting('app.tenant_id')::int)"))
            await c.execute(text(f"grant select, insert, update on {t} to app"))
        await c.execute(text("grant usage on all sequences in schema public to app"))
        await c.execute(text("insert into cap_series (tenant_id, series) select g, '1C26TMK' "
                             f"from generate_series(1, {n_tenants}) g"))
    await eng.dispose()


# ---------------------------------------------------------------- app
engine = create_async_engine(PG_DSN_APP, pool_size=int(os.environ.get("POOL", "8")), max_overflow=0, pool_timeout=2)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
rds = aredis.from_url(REDIS_URL)
PUBLIC_KEY = serialization.load_pem_public_key((KEYS / "public.pem").read_bytes()) if (KEYS / "public.pem").exists() else None
GCRA = """
local t = redis.call('TIME'); local now = tonumber(t[1]) + tonumber(t[2]) / 1e6
local tat = tonumber(redis.call('GET', KEYS[1]) or now)
if tat < now then tat = now end
if tat - now > tonumber(ARGV[2]) then return 0 end
redis.call('SET', KEYS[1], tat + tonumber(ARGV[1]), 'PX', math.ceil((tat + tonumber(ARGV[1]) - now) * 1000) + 1000)
return 1
"""
gcra = rds.register_script(GCRA)


class Principal(BaseModel):
    model_config = ConfigDict(frozen=True)
    sub: str
    tenant_id: int = Field(alias="tid", gt=0)
    scopes: frozenset[str] = Field(alias="scope")

    @field_validator("scopes", mode="before")
    @classmethod
    def _split(cls, v: str) -> frozenset[str]:
        return frozenset(v.split())


bearer = HTTPBearer(auto_error=False)


async def current_principal(security_scopes: SecurityScopes,
                            cred: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> Principal:
    if cred is None:
        raise HTTPException(401, "token không hợp lệ", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = jwt.decode(cred.credentials, PUBLIC_KEY, algorithms=["EdDSA"], audience="invoice-api",
                            issuer="https://id.mekong.vn", options={"require": ["exp", "sub", "aud", "iss"]})
        p = Principal.model_validate(claims)
    except (jwt.PyJWTError, ValidationError):
        raise HTTPException(401, "token không hợp lệ", headers={"WWW-Authenticate": "Bearer"}) from None
    if set(security_scopes.scopes) - p.scopes:
        raise HTTPException(403, "thiếu scope")
    return p


async def rate_limit(p: Annotated[Principal, Security(current_principal, scopes=["invoice:write"])]) -> Principal:
    rate, burst = 200, 400                                          # mỗi tenant: 200 hóa đơn/s, burst 400
    try:
        ok = await gcra(keys=[f"rl:{p.tenant_id}"], args=[1 / rate, (burst - 1) / rate])
    except aredis.RedisError:
        ok = 1                                                      # fail open cho invoice-api (M11)
    if not ok:
        raise HTTPException(429, "vượt hạn mức", headers={"Retry-After": "1"})
    return p


DB_LAYER = os.environ.get("DB_LAYER", "sqlalchemy")         # "sqlalchemy" | "asyncpg"
_PARAM = re.compile(r"(?<!:):([a-z_]+)")


class Tx:
    """Bộ chuyển tối giản: cùng câu SQL (tham số :tên) chạy qua SQLAlchemy text() hoặc asyncpg thuần ($1…)."""

    def __init__(self, conn):
        self.conn = conn

    @staticmethod
    def _pg(sql, params):
        names = list(dict.fromkeys(_PARAM.findall(sql)))
        q = _PARAM.sub(lambda m: f"${names.index(m.group(1)) + 1}", sql)
        return q, names

    async def scalar(self, sql, params=None):
        if DB_LAYER == "asyncpg":
            q, names = self._pg(sql, params or {})
            return await self.conn.fetchval(q, *[(params or {})[n] for n in names])
        return await self.conn.scalar(text(sql), params or {})

    async def execute(self, sql, params=None):
        if DB_LAYER == "asyncpg":
            q, names = self._pg(sql, params if isinstance(params, dict) else (params or [{}])[0])
            if isinstance(params, list):
                return await self.conn.executemany(q, [[p[n] for n in names] for p in params])
            return await self.conn.execute(q, *[(params or {})[n] for n in names])
        return await self.conn.execute(text(sql), params or {})

    async def one(self, sql, params):
        if DB_LAYER == "asyncpg":
            q, names = self._pg(sql, params)
            return dict(await self.conn.fetchrow(q, *[params[n] for n in names]))
        return dict((await self.conn.execute(text(sql), params)).one()._mapping)


_apg_pool = None


async def tenant_session(p: Annotated[Principal, Depends(rate_limit)]) -> AsyncIterator[Tx]:
    global _apg_pool
    if DB_LAYER == "asyncpg":
        if _apg_pool is None:
            import asyncpg
            _apg_pool = await asyncpg.create_pool(host="/tmp", port=5433, user="app", database="bench",
                                                  min_size=int(os.environ.get("POOL", "8")),
                                                  max_size=int(os.environ.get("POOL", "8")))
        async with _apg_pool.acquire() as conn, conn.transaction():
            await conn.execute("select set_config('app.tenant_id', $1, true)", str(p.tenant_id))
            yield Tx(conn)
        return
    async with SessionLocal() as s, s.begin():
        await s.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(p.tenant_id)})
        yield Tx(s)


class InvoiceCreate(InvoiceIn):
    number: int | None = None                                       # server cấp số; trường của client bị bỏ qua


class InvoiceOut(BaseModel):
    id: int
    series: str
    number: int
    total: int


class InFlightLimit:
    def __init__(self, app, limit):
        self.app, self.limit, self.n = app, limit, 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or self.n < self.limit:
            if scope["type"] == "http":
                self.n += 1
            try:
                return await self.app(scope, receive, send)
            finally:
                if scope["type"] == "http":
                    self.n -= 1
        await send({"type": "http.response.start", "status": 503, "headers": [(b"retry-after", b"1"),
                                                                              (b"content-length", b"0")]})
        await send({"type": "http.response.body", "body": b""})


app = FastAPI(title="invoice-api (capstone)")
if os.environ.get("SHED"):
    app.add_middleware(InFlightLimit, limit=int(os.environ["SHED"]))


@app.get("/health/live")
async def live():
    return {"ok": True}


@app.post("/v1/invoices", status_code=201, response_model=InvoiceOut,
          responses={401: {}, 403: {}, 409: {}, 422: {}, 429: {}, 503: {}})
async def create_invoice(request: Request, db: Annotated[Tx, Depends(tenant_session, scope="function")],
                         p: Annotated[Principal, Depends(rate_limit)],
                         idempotency_key: Annotated[UUID, Header()]):
    raw = await request.body()
    try:
        inv = InvoiceCreate.model_validate_json(raw)                  # body thô → jiter (M06)
    except ValidationError as e:
        return JSONResponse({"type": "about:blank", "title": "Dữ liệu không hợp lệ",
                             "errors": e.errors(include_url=False, include_context=False)}, status_code=422)
    req_hash = hashlib.sha256(inv.model_dump_json().encode()).hexdigest()
    claimed = await db.scalar(
        "insert into cap_idempotency(tenant_id, key, request_hash) values (:t, :k, :h) "
        "on conflict (tenant_id, key) do nothing returning key", {"t": p.tenant_id, "k": idempotency_key, "h": req_hash})
    if claimed is None:
        row = await db.one("select request_hash, status_code, response_body from cap_idempotency "
                           "where tenant_id = :t and key = :k", {"t": p.tenant_id, "k": idempotency_key})
        if row["request_hash"] != req_hash:
            return JSONResponse({"title": "Idempotency-Key đã dùng cho payload khác"}, status_code=422)
        body = row["response_body"]
        body = json.loads(body) if isinstance(body, str) else body                  # asyncpg trả jsonb dạng chuỗi
        return JSONResponse(body, status_code=row["status_code"], headers={"Idempotent-Replayed": "true"})
    inv_id = await db.scalar(
        "insert into cap_invoices (tenant_id, series, number, seller_tax_code, buyer_name, issued_at, "
        "total_before_tax, total_tax, total) values (:t, :s, 0, :st, :b, :ia, :tb, :tt, :tot) returning id",
        {"t": p.tenant_id, "s": inv.series, "st": str(inv.seller_tax_code), "b": inv.buyer.name, "ia": inv.issued_at,
         "tb": inv.total_before_tax, "tt": inv.total_tax, "tot": inv.total})
    await db.execute(
        "insert into cap_lines (invoice_id, tenant_id, line_no, name, quantity, unit_price, vat_rate, amount) "
        "values (:i, :t, :n, :nm, :q, :u, :v, :a)",
        [dict(i=inv_id, t=p.tenant_id, n=l.line_no, nm=l.name, q=l.quantity, u=l.unit_price, v=l.vat_rate, a=l.amount)
         for l in inv.lines])
    number = await db.scalar(                                        # cấp số CUỐI transaction (M10)
        "update cap_series set last_number = last_number + 1 where tenant_id = :t and series = :s "
        "returning last_number", {"t": p.tenant_id, "s": inv.series})
    if number is None:
        raise HTTPException(409, "ký hiệu hóa đơn chưa đăng ký")
    await db.execute("update cap_invoices set number = :n where id = :i", {"n": number, "i": inv_id})
    out = InvoiceOut(id=inv_id, series=inv.series, number=number, total=inv.total)
    body = out.model_dump(mode="json")
    await db.execute("insert into cap_outbox (tenant_id, topic, payload) values (:t, 'invoice.created', "
                     "cast(:p as jsonb))", {"t": p.tenant_id, "p": json.dumps(body)})
    await db.execute("update cap_idempotency set status_code = 201, response_body = cast(:b as jsonb) "
                     "where tenant_id = :t and key = :k", {"b": json.dumps(body), "t": p.tenant_id, "k": idempotency_key})
    return out


def make_keys_and_tokens(n_tenants=50):
    import time
    from cryptography.hazmat.primitives.asymmetric import ed25519
    KEYS.mkdir(parents=True, exist_ok=True)
    priv = ed25519.Ed25519PrivateKey.generate()
    (KEYS / "public.pem").write_bytes(priv.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    now = int(time.time())
    toks = [jwt.encode({"sub": f"pos-{t}", "tid": t, "scope": "invoice:read invoice:write", "aud": "invoice-api",
                        "iss": "https://id.mekong.vn", "iat": now, "exp": now + 7200}, priv, algorithm="EdDSA")
            for t in range(1, n_tenants + 1)]
    (KEYS / "tokens.json").write_text(json.dumps(toks))


if __name__ == "__main__" and sys.argv[1:] == ["init"]:
    import asyncio
    make_keys_and_tokens()
    asyncio.run(init_db())
    print("đã tạo schema, role app, RLS, khóa và token")
