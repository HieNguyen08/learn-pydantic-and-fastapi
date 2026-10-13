"""Các phép đo phụ: chi phí dựng schema, serialization, đường lỗi, băm mật khẩu, N+1.

Chạy:  python bench_misc.py [--only schema ser err hash nplus1]
Ghi:   results/misc.json
"""
import argparse
import asyncio
import hashlib
import json
import statistics
import sys
import time
import timeit
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from impls import _pydantic_v2_models, make_msgspec  # noqa: E402
from payload import make_invoice, payload_bytes  # noqa: E402


def per_call_us(fn, repeat=7):
    t = timeit.Timer(fn)
    n, _ = t.autorange()
    return statistics.median(x / n for x in t.repeat(repeat, n)) * 1e6


# ---------------------------------------------------------------- dựng schema
def bench_schema(res):
    from typing import Annotated

    from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

    def define(k, defer=False):
        ns = {"__annotations__": {f"f{i}": Annotated[int, Field(ge=0)] for i in range(k)}}
        if defer:
            ns["model_config"] = ConfigDict(defer_build=True)
        return type(f"M{k}", (BaseModel,), ns)

    rows = []
    for k in (5, 10, 25, 50, 100, 200):
        us = per_call_us(lambda: define(k), repeat=5)
        usd = per_call_us(lambda: define(k, defer=True), repeat=5)
        M = define(k)
        data = {f"f{i}": i for i in range(k)}
        val = per_call_us(lambda: M.model_validate(data))
        rows.append(dict(fields=k, build_us=us, build_defer_us=usd, validate_us=val))
        print(f"schema k={k:3d} build={us:9.1f}µs defer={usd:8.1f}µs validate={val:6.2f}µs")
    # toàn bộ model hóa đơn (3 class lồng nhau, có validator)
    inv_build = per_call_us(lambda: _pydantic_v2_models("full"), repeat=5)
    Inv = _pydantic_v2_models("full")
    ta_build = per_call_us(lambda: TypeAdapter(list[Inv]), repeat=5)
    res["schema"] = dict(rows=rows, invoice_build_us=inv_build, typeadapter_list_build_us=ta_build)
    print(f"invoice models build={inv_build:.0f}µs, TypeAdapter(list[Invoice])={ta_build:.0f}µs")


# ---------------------------------------------------------------- serialization
def bench_ser(res):
    import msgspec
    import orjson
    Inv = _pydantic_v2_models("schema")
    dec = make_msgspec("schema")
    rows = []
    for n in (1, 12, 50, 200):
        raw = payload_bytes(n)
        m = Inv.model_validate_json(raw)
        s = dec(raw)
        cases = {
            "model_dump_json()": lambda: m.model_dump_json(),
            "model_dump() + json.dumps": lambda: json.dumps(m.model_dump(), default=str),
            "model_dump(mode='json') + orjson": lambda: orjson.dumps(m.model_dump(mode="json")),
            "model_dump() (python)": lambda: m.model_dump(),
            "msgspec.json.encode": lambda: msgspec.json.encode(s),
        }
        for k, f in cases.items():
            us = per_call_us(f)
            rows.append(dict(case=k, lines=n, us=us))
            print(f"ser {k:34s} n={n:3d} {us:8.1f}µs")
    res["ser"] = rows


# ---------------------------------------------------------------- đường lỗi
def bench_err(res):
    from pydantic import ValidationError
    Inv = _pydantic_v2_models("schema")
    ok = make_invoice(12)
    one = json.loads(json.dumps(ok)); one["lines"][5]["quantity"] = "abc"
    many = json.loads(json.dumps(ok))
    for l in many["lines"]:
        l["vat_rate"] = "7"; l["quantity"] = -1
    cases = {"hợp lệ": ok, "1 lỗi (lines[5].quantity)": one, "24 lỗi (mọi dòng sai 2 trường)": many}
    rows = []
    for k, d in cases.items():
        raw = json.dumps(d).encode()

        def f():
            try:
                Inv.model_validate_json(raw)
            except ValidationError as e:
                return e.error_count()

        def g():
            try:
                Inv.model_validate_json(raw)
            except ValidationError as e:
                return e.json()
        rows.append(dict(case=k, validate_us=per_call_us(f), with_json_errors_us=per_call_us(g)))
        print("err", rows[-1])
    res["err"] = rows


# ---------------------------------------------------------------- băm mật khẩu
def bench_hash(res):
    import bcrypt
    from argon2 import PasswordHasher
    pw = b"Mekong-Cloud-2026!"
    rows = []

    def timeit_ms(f, n):
        ts = []
        for _ in range(n):
            t0 = time.perf_counter(); f(); ts.append(time.perf_counter() - t0)
        return statistics.median(ts) * 1000

    rows.append(dict(alg="SHA-256 (KHÔNG dùng cho mật khẩu)", ms=timeit_ms(lambda: hashlib.sha256(pw).digest(), 2000), mem_mib=0))
    rows.append(dict(alg="PBKDF2-SHA256 600k vòng", ms=timeit_ms(lambda: hashlib.pbkdf2_hmac("sha256", pw, b"salt" * 4, 600_000), 5), mem_mib=0))
    for cost in (10, 12):
        salt = bcrypt.gensalt(cost)
        rows.append(dict(alg=f"bcrypt cost={cost}", ms=timeit_ms(lambda: bcrypt.hashpw(pw, salt), 5), mem_mib=0.004))
    for (m, t, p, label) in [(19456, 2, 1, "Argon2id m=19MiB t=2 p=1 (OWASP)"),
                             (47104, 1, 1, "Argon2id m=46MiB t=1 p=1 (OWASP)"),
                             (65536, 3, 4, "Argon2id m=64MiB t=3 p=4 (RFC 9106 low-mem)")]:
        ph = PasswordHasher(time_cost=t, memory_cost=m, parallelism=p)
        rows.append(dict(alg=label, ms=timeit_ms(lambda: ph.hash(pw), 7), mem_mib=m / 1024))
    for r in rows:
        print(f"hash {r['alg']:45s} {r['ms']:9.3f} ms")
    res["hash"] = rows


# ---------------------------------------------------------------- N+1
def bench_nplus1(res):
    from sqlalchemy import ForeignKey, String, event, select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.orm import DeclarativeBase, Mapped, joinedload, mapped_column, relationship, selectinload

    class Base(DeclarativeBase):
        pass

    class InvoiceRow(Base):
        __tablename__ = "invoices"
        id: Mapped[int] = mapped_column(primary_key=True)
        tenant_id: Mapped[int]
        total: Mapped[int]
        lines: Mapped[list["LineRow"]] = relationship(back_populates="invoice")

    class LineRow(Base):
        __tablename__ = "invoice_lines"
        id: Mapped[int] = mapped_column(primary_key=True)
        invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
        name: Mapped[str] = mapped_column(String(500))
        amount: Mapped[int]
        invoice: Mapped[InvoiceRow] = relationship(back_populates="lines")

    async def run():
        db = HERE / "results" / "nplus1.sqlite"
        db.unlink(missing_ok=True)
        eng = create_async_engine(f"sqlite+aiosqlite:///{db}")
        counter = {"n": 0}
        event.listen(eng.sync_engine, "before_cursor_execute", lambda *a, **k: counter.__setitem__("n", counter["n"] + 1))
        async with eng.begin() as c:
            await c.run_sync(Base.metadata.create_all)
        S = async_sessionmaker(eng, expire_on_commit=False)
        async with S() as s:
            for i in range(1, 201):
                inv = InvoiceRow(id=i, tenant_id=1, total=0)
                inv.lines = [LineRow(name=f"Hàng {j}", amount=1000 * j) for j in range(12)]
                s.add(inv)
            await s.commit()

        async def nplus1(s: AsyncSession, n):
            invs = (await s.scalars(select(InvoiceRow).limit(n))).all()
            out = 0
            for inv in invs:  # mỗi hóa đơn một truy vấn — mẫu N+1 viết tay
                lines = (await s.scalars(select(LineRow).where(LineRow.invoice_id == inv.id))).all()
                out += sum(l.amount for l in lines)
            return out

        async def selectin(s, n):
            invs = (await s.scalars(select(InvoiceRow).options(selectinload(InvoiceRow.lines)).limit(n))).all()
            return sum(l.amount for inv in invs for l in inv.lines)

        async def joined(s, n):
            invs = (await s.scalars(select(InvoiceRow).options(joinedload(InvoiceRow.lines)).limit(n))).unique().all()
            return sum(l.amount for inv in invs for l in inv.lines)

        rows = []
        for name, f in (("N+1 (mỗi hóa đơn 1 query)", nplus1), ("selectinload (2 query)", selectin), ("joinedload (1 query JOIN)", joined)):
            for n in (10, 50, 200):
                ts = []
                for _ in range(7):
                    async with S() as s:
                        counter["n"] = 0
                        t0 = time.perf_counter()
                        await f(s, n)
                        ts.append(time.perf_counter() - t0)
                        q = counter["n"]
                rows.append(dict(strategy=name, invoices=n, ms=statistics.median(ts) * 1000, queries=q))
                print(f"nplus1 {name:28s} n={n:3d} {rows[-1]['ms']:7.2f} ms  queries={q}")
        await eng.dispose()
        db.unlink(missing_ok=True)
        return rows

    res["nplus1"] = asyncio.run(run())


EXPS = dict(schema=bench_schema, ser=bench_ser, err=bench_err, hash=bench_hash, nplus1=bench_nplus1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    out = HERE / "results" / "misc.json"
    out.parent.mkdir(exist_ok=True)
    res = json.loads(out.read_text()) if out.exists() else {}
    for k, f in EXPS.items():
        if a.only and k not in a.only:
            continue
        f(res)
        out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print("→", out)


if __name__ == "__main__":
    main()
