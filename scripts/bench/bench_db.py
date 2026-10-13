"""Thí nghiệm database cho Module 10 — PostgreSQL thật + SQLAlchemy 2.x async + asyncpg.

Yêu cầu: một PostgreSQL chạy sẵn, chuỗi kết nối qua biến môi trường PG_DSN
(mặc định postgresql+asyncpg://postgres@/bench?host=/tmp&port=5433).

  d1  N+1 so với selectinload / joinedload (đếm truy vấn, thời gian)
  d2  cấp số hóa đơn liên tục khi nhiều request đồng thời: MAX()+1, khóa hàng (FOR UPDATE), sequence
  d3  idempotency key: kiểm tra-rồi-ghi so với INSERT … ON CONFLICT, 50 request trùng khóa đồng thời
  d4  Row-Level Security: cùng một truy vấn không WHERE, hai tenant thấy hai tập dữ liệu
  d4leak  SET cấp session rò sang request sau qua pool, SET LOCAL thì không
  d5  kích thước pool: 64 client, truy vấn tốn CPU, pool 1…64
  d6  migration: ALTER TABLE xếp hàng sau transaction dài làm nghẽn mọi SELECT; lock_timeout
  d7  outbox relay: FOR UPDATE so với FOR UPDATE SKIP LOCKED, 1/2/4 relay
  d8  thời gian giữ kết nối của một transaction POST hóa đơn đầy đủ (đầu vào cho định luật Little)
Chạy:  python bench_db.py [--only d1 d2] → results/db.json
"""
import argparse
import asyncio
import json
import os
import statistics
import time
import uuid
from pathlib import Path

from sqlalchemy import ForeignKey, String, event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, joinedload, mapped_column, relationship, selectinload

HERE = Path(__file__).parent
DSN = os.environ.get("PG_DSN", "postgresql+asyncpg://postgres@/bench?host=/tmp&port=5433")
_base, _query = DSN.split("?", 1)
ADMIN_DSN = _base.rsplit("/", 1)[0] + "/postgres?" + _query


async def ensure_db():
    eng = create_async_engine(ADMIN_DSN, isolation_level="AUTOCOMMIT")
    async with eng.connect() as c:
        exists = await c.scalar(text("select 1 from pg_database where datname='bench'"))
        if not exists:
            await c.execute(text("create database bench"))
    await eng.dispose()


class Base(DeclarativeBase):
    pass


class InvoiceRow(Base):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    series: Mapped[str] = mapped_column(String(10))
    number: Mapped[int]
    total: Mapped[int]
    lines: Mapped[list["LineRow"]] = relationship(back_populates="invoice")


class LineRow(Base):
    __tablename__ = "invoice_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    name: Mapped[str] = mapped_column(String(500))
    amount: Mapped[int]
    invoice: Mapped[InvoiceRow] = relationship(back_populates="lines")


# ---------------------------------------------------------------- d1: N+1
async def d1_nplus1(eng, res):
    async with eng.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
    S = async_sessionmaker(eng, expire_on_commit=False)
    async with S() as s:
        for i in range(1, 201):
            inv = InvoiceRow(id=i, tenant_id=1, series="1C26TMK", number=i, total=0)
            inv.lines = [LineRow(name=f"Hàng {j}", amount=1000 * j) for j in range(12)]
            s.add(inv)
        await s.commit()
    counter = {"n": 0}

    def count(*a, **k):
        counter["n"] += 1
    event.listen(eng.sync_engine, "before_cursor_execute", count)

    async def nplus1(s, n):
        invs = (await s.scalars(select(InvoiceRow).limit(n))).all()
        for inv in invs:
            (await s.scalars(select(LineRow).where(LineRow.invoice_id == inv.id))).all()

    async def selectin(s, n):
        (await s.scalars(select(InvoiceRow).options(selectinload(InvoiceRow.lines)).limit(n))).all()

    async def joined(s, n):
        (await s.scalars(select(InvoiceRow).options(joinedload(InvoiceRow.lines)).limit(n))).unique().all()

    rows = []
    for name, f in (("N+1", nplus1), ("selectinload", selectin), ("joinedload", joined)):
        for n in (10, 50, 200):
            ts = []
            for _ in range(9):
                async with S() as s:
                    counter["n"] = 0
                    t0 = time.perf_counter()
                    await f(s, n)
                    ts.append((time.perf_counter() - t0) * 1000)
                    q = counter["n"]
            rows.append(dict(strategy=name, invoices=n, ms=min(ts), queries=q))
            print(f"d1 {name:13s} n={n:3d} {min(ts):7.2f} ms  {q} truy vấn")
    event.remove(eng.sync_engine, "before_cursor_execute", count)
    res["d1_nplus1"] = rows


# ---------------------------------------------------------------- d2: cấp số hóa đơn
DDL_D2 = """
drop table if exists inv_numbers, series_counter;
drop sequence if exists inv_seq;
create table inv_numbers (id bigserial primary key, series text not null, number int not null);
create table series_counter (series text primary key, last_number int not null);
insert into series_counter values ('1C26TMK', 0);
create sequence inv_seq;
"""


async def d2_numbering(eng, res, n_req=400, conc=32):
    async with eng.begin() as c:
        for stmt in DDL_D2.strip().split(";"):
            if stmt.strip():
                await c.execute(text(stmt))
    S = async_sessionmaker(eng)

    async def max_plus_one():
        async with S() as s, s.begin():
            nxt = (await s.scalar(text("select coalesce(max(number),0)+1 from inv_numbers where series='1C26TMK'")))
            await asyncio.sleep(0)            # một "khoảng hở" rất nhỏ giữa đọc và ghi, như code thật
            await s.execute(text("insert into inv_numbers(series, number) values ('1C26TMK', :n)"), {"n": nxt})

    async def row_lock():
        async with S() as s, s.begin():
            nxt = await s.scalar(text(
                "update series_counter set last_number = last_number + 1 where series='1C26TMK' returning last_number"))
            await s.execute(text("insert into inv_numbers(series, number) values ('1C26TMK', :n)"), {"n": nxt})

    async def sequence():
        async with S() as s, s.begin():
            nxt = await s.scalar(text("select nextval('inv_seq')"))
            await s.execute(text("insert into inv_numbers(series, number) values ('1C26TMK', :n)"), {"n": nxt})

    async def sequence_with_rollbacks():
        # 5% giao dịch bị hủy sau khi đã lấy số (lỗi nghiệp vụ, timeout…)
        async with S() as s:
            await s.begin()
            nxt = await s.scalar(text("select nextval('inv_seq')"))
            await s.execute(text("insert into inv_numbers(series, number) values ('1C26TMK', :n)"), {"n": nxt})
            if nxt % 20 == 0:
                await s.rollback()
            else:
                await s.commit()

    rows = []
    for name, f in (("MAX()+1", max_plus_one), ("UPDATE … RETURNING (khóa hàng)", row_lock),
                    ("sequence", sequence), ("sequence + 5% rollback", sequence_with_rollbacks)):
        async with eng.begin() as c:
            for stmt in ("truncate inv_numbers", "update series_counter set last_number=0", "alter sequence inv_seq restart"):
                await c.execute(text(stmt))
        sem = asyncio.Semaphore(conc)

        async def one():
            async with sem:
                await f()
        t0 = time.perf_counter()
        await asyncio.gather(*(one() for _ in range(n_req)))
        dt = time.perf_counter() - t0
        async with eng.connect() as c:
            total = await c.scalar(text("select count(*) from inv_numbers"))
            distinct = await c.scalar(text("select count(distinct number) from inv_numbers"))
            mx = await c.scalar(text("select max(number) from inv_numbers"))
        dup = total - distinct
        gaps = mx - distinct
        rows.append(dict(method=name, requests=n_req, concurrency=conc, rows=total, duplicates=dup, gaps=gaps,
                         per_s=n_req / dt))
        print(f"d2 {name:32s} hàng={total} trùng={dup} khoảng trống={gaps} {n_req / dt:7.0f} giao dịch/s")
    res["d2_numbering"] = rows


# ---------------------------------------------------------------- d3: idempotency
DDL_D3 = """
drop table if exists idem_invoices, idempotency_keys, idempotency_keys_nouniq;
create table idem_invoices (id bigserial primary key, tenant_id int not null, payload_hash text not null);
create table idempotency_keys (
  tenant_id int not null, key uuid not null, request_hash text not null,
  invoice_id bigint, created_at timestamptz not null default now(),
  primary key (tenant_id, key));
create table idempotency_keys_nouniq (tenant_id int not null, key uuid not null, invoice_id bigint);
"""


async def d3_idempotency(eng, res, dup=50, trials=20):
    async with eng.begin() as c:
        for stmt in DDL_D3.strip().split(";"):
            if stmt.strip():
                await c.execute(text(stmt))
    S = async_sessionmaker(eng)

    async def check_then_insert_no_constraint(key):
        async with S() as s, s.begin():
            found = await s.scalar(text("select invoice_id from idempotency_keys_nouniq where tenant_id=1 and key=:k"),
                                   {"k": key})
            if found:
                return "replay"
            await asyncio.sleep(0.002)          # xử lý nghiệp vụ (validate, tính thuế…)
            inv = await s.scalar(text("insert into idem_invoices(tenant_id, payload_hash) values (1,'h') returning id"))
            await s.execute(text("insert into idempotency_keys_nouniq values (1,:k,:i)"), {"k": key, "i": inv})
            return "created"

    async def check_then_insert_unique(key):
        try:
            async with S() as s, s.begin():
                found = await s.scalar(text("select invoice_id from idempotency_keys where tenant_id=1 and key=:k"),
                                       {"k": key})
                if found:
                    return "replay"
                await asyncio.sleep(0.002)
                inv = await s.scalar(text("insert into idem_invoices(tenant_id, payload_hash) values (1,'h') returning id"))
                await s.execute(text("insert into idempotency_keys(tenant_id,key,request_hash,invoice_id) "
                                     "values (1,:k,'h',:i)"), {"k": key, "i": inv})
                return "created"
        except IntegrityError:
            return "error"                      # cả transaction rollback → client nhận 500

    async def claim_first(key):
        async with S() as s, s.begin():
            claimed = await s.scalar(text(
                "insert into idempotency_keys(tenant_id,key,request_hash) values (1,:k,'h') "
                "on conflict (tenant_id,key) do nothing returning key"), {"k": key})
            if claimed is None:
                return "replay"                 # khóa đã có chủ → trả response đã lưu hoặc 409 nếu đang xử lý
            await asyncio.sleep(0.002)
            inv = await s.scalar(text("insert into idem_invoices(tenant_id, payload_hash) values (1,'h') returning id"))
            await s.execute(text("update idempotency_keys set invoice_id=:i where tenant_id=1 and key=:k"),
                            {"i": inv, "k": key})
            return "created"

    rows = []
    for name, f in (("SELECT rồi INSERT, không ràng buộc unique", check_then_insert_no_constraint),
                    ("SELECT rồi INSERT, có PRIMARY KEY (tenant_id, key)", check_then_insert_unique),
                    ("INSERT … ON CONFLICT DO NOTHING trước, xử lý sau", claim_first)):
        created_total = 0
        outcomes = {}
        for _ in range(trials):
            async with eng.begin() as c:
                await c.execute(text("truncate idem_invoices, idempotency_keys, idempotency_keys_nouniq"))
            key = str(uuid.uuid4())
            outs = await asyncio.gather(*(f(key) for _ in range(dup)))
            for o in outs:
                outcomes[o] = outcomes.get(o, 0) + 1
            async with eng.connect() as c:
                created_total += await c.scalar(text("select count(*) from idem_invoices"))
        outcomes = {k: v / trials for k, v in outcomes.items()}
        rows.append(dict(method=name, trials=trials, duplicates_per_trial=dup,
                         invoices_per_key=created_total / trials, outcomes=outcomes))
        print(f"d3 {name:50s} hóa đơn/khóa = {created_total / trials:5.1f}   kết cục TB: {outcomes}")
    res["d3_idempotency"] = rows


# ---------------------------------------------------------------- d4: RLS
DDL_D4 = """
drop table if exists rls_invoices;
drop role if exists app_user;
create role app_user;
create table rls_invoices (id bigserial primary key, tenant_id int not null, total int not null);
insert into rls_invoices(tenant_id,total) select (g % 3) + 1, g * 1000 from generate_series(1, 30) g;
alter table rls_invoices enable row level security;
create policy tenant_isolation on rls_invoices
  using (tenant_id = current_setting('app.tenant_id')::int);
grant select on rls_invoices to app_user;
"""


async def d4_rls(eng, res):
    async with eng.begin() as c:
        for stmt in DDL_D4.strip().split(";"):
            if stmt.strip():
                await c.execute(text(stmt))
    out = []
    for tenant in (1, 2):
        async with eng.begin() as c:
            await c.execute(text("set local role app_user"))
            await c.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
            n = await c.scalar(text("select count(*) from rls_invoices"))        # KHÔNG có WHERE tenant_id
            ids = (await c.execute(text("select distinct tenant_id from rls_invoices"))).scalars().all()
        out.append(dict(tenant=tenant, rows_visible=n, tenants_seen=list(ids)))
        print(f"d4 tenant {tenant}: thấy {n} hàng, tenant_id xuất hiện: {list(ids)}")
    res["d4_rls"] = out


async def d4_leak(res):
    """Pool trả kết nối về rồi cho request sau dùng lại: SET cấp session có rò sang request sau không?"""
    eng = create_async_engine(DSN, pool_size=1, max_overflow=0)
    out = {}
    for mode, is_local in (("set_config(..., is_local=false)  ~ SET", "false"),
                           ("set_config(..., is_local=true)   ~ SET LOCAL", "true")):
        async with eng.begin() as c:                                   # request 1 của tenant 1
            await c.execute(text(f"select set_config('app.tenant_id', '1', {is_local})"))
        async with eng.begin() as c:                                   # request 2: quên đặt tenant
            await c.execute(text("set local role app_user"))
            seen = await c.scalar(text("select current_setting('app.tenant_id', true)"))
            try:
                n = await c.scalar(text("select count(*) from rls_invoices"))
            except Exception as e:  # noqa: BLE001
                n = "lỗi: " + str(getattr(e, "orig", e)).splitlines()[0].split(">: ", 1)[-1]
        out[mode] = dict(setting_seen_by_next_request=seen, rows_visible=n)
        print(f"d4 rò rỉ {mode}: request sau thấy app.tenant_id={seen!r}, đọc được {n} hàng")
        await eng.dispose()
    res["d4_leak"] = out


# ---------------------------------------------------------------- d6: migration và hàng đợi khóa
async def d6_lock_queue(res):
    """Một transaction đọc dài + ALTER TABLE: mọi SELECT sau đó xếp hàng sau ALTER."""
    eng = create_async_engine(DSN, pool_size=20, max_overflow=0)
    async with eng.begin() as c:
        await c.execute(text("drop table if exists mig_invoices"))
        await c.execute(text("create table mig_invoices (id bigserial primary key, total int)"))
        await c.execute(text("insert into mig_invoices(total) select g from generate_series(1, 1000) g"))
    out = []
    for label, lock_timeout in (("ALTER TABLE không lock_timeout", None), ("ALTER TABLE với lock_timeout = 100ms", "100ms")):
        lat = []
        alter_result = {}

        async def long_reader():
            async with eng.begin() as c:
                await c.execute(text("select count(*) from mig_invoices"))   # giữ ACCESS SHARE tới hết transaction
                await asyncio.sleep(2.0)                                     # ví dụ: báo cáo chạy lâu

        async def migrate():
            await asyncio.sleep(0.2)
            t0 = time.perf_counter()
            try:
                async with eng.begin() as c:
                    if lock_timeout:
                        await c.execute(text(f"set local lock_timeout = '{lock_timeout}'"))
                    await c.execute(text("alter table mig_invoices add column note text"))
                alter_result.update(ok=True)
            except Exception as e:  # noqa: BLE001
                alter_result.update(ok=False, error=str(getattr(e, "orig", e)).splitlines()[0].split(">: ", 1)[-1])
            alter_result["ms"] = (time.perf_counter() - t0) * 1000

        async def one_read(start):
            t0 = time.perf_counter()
            async with eng.connect() as c:
                await c.execute(text("select total from mig_invoices where id = 1"))
            lat.append(dict(t=t0 - start, ms=(time.perf_counter() - t0) * 1000))

        async def api_reads(start):
            # request API đến đều đặn mỗi 100 ms, độc lập nhau (open-loop), như traffic thật
            await asyncio.sleep(0.3)
            tasks = []
            for _ in range(30):
                tasks.append(asyncio.create_task(one_read(start)))
                await asyncio.sleep(0.1)
            await asyncio.gather(*tasks)

        async with eng.begin() as c:
            await c.execute(text("alter table mig_invoices drop column if exists note"))
        start = time.perf_counter()
        await asyncio.gather(long_reader(), migrate(), api_reads(start))
        lat.sort(key=lambda r: r["t"])
        mx = max(r["ms"] for r in lat)
        out.append(dict(case=label, alter=alter_result, reads=lat, max_read_ms=mx))
        print(f"d6 {label:36s} ALTER: {alter_result}  SELECT chậm nhất: {mx:7.1f} ms")
    res["d6_lock_queue"] = out
    await eng.dispose()


# ---------------------------------------------------------------- d7: outbox relay
async def d7_outbox(res, n_events=4000, batch=100):
    eng = create_async_engine(DSN, pool_size=10, max_overflow=0)
    out = []
    for label, lock in (("FOR UPDATE (không SKIP LOCKED)", "for update"), ("FOR UPDATE SKIP LOCKED", "for update skip locked")):
        for relays in (1, 2, 4):
            async with eng.begin() as c:
                await c.execute(text("drop table if exists outbox"))
                await c.execute(text("create table outbox (id bigserial primary key, payload text, published_at timestamptz)"))
                await c.execute(text(f"insert into outbox(payload) select 'evt-' || g from generate_series(1, {n_events}) g"))
            published = []

            async def relay():
                while True:
                    async with eng.begin() as c:
                        ids = (await c.execute(text(
                            f"select id from outbox where published_at is null order by id limit {batch} {lock}"))).scalars().all()
                        if not ids:
                            return
                        await asyncio.sleep(0.005)          # gửi lên broker (Kafka/NATS…) ~5 ms mỗi lô
                        published.extend(ids)
                        await c.execute(text("update outbox set published_at = now() where id = any(:ids)"), {"ids": list(ids)})
            t0 = time.perf_counter()
            await asyncio.gather(*(relay() for _ in range(relays)))
            dt = time.perf_counter() - t0
            dup = len(published) - len(set(published))
            r = dict(lock=label, relays=relays, events_per_s=n_events / dt, duplicates=dup)
            out.append(r)
            print(f"d7 {label:32s} relay={relays} {r['events_per_s']:7.0f} sự kiện/s  trùng={dup}")
    res["d7_outbox"] = out
    await eng.dispose()


# ---------------------------------------------------------------- d5: kích thước pool
async def d5_pool(res, clients=64, per_client=25):
    """64 coroutine cùng gửi truy vấn tốn CPU phía Postgres (~20 ms khi chạy một mình); đổi pool_size.
    Đo thông lượng, độ trễ request (gồm chờ pool) và thời gian chạy truy vấn trong DB."""
    q = text("select count(*) from generate_series(1, 150000)")
    rows = []
    for pool in (1, 2, 4, 8, 16, 32, 64):
        eng = create_async_engine(DSN, pool_size=pool, max_overflow=0, pool_timeout=120)
        async with eng.connect() as c:                       # làm ấm
            await c.execute(q)
        lat, dbt = [], []

        async def client():
            for _ in range(per_client):
                t0 = time.perf_counter()
                async with eng.connect() as c:
                    t1 = time.perf_counter()
                    await c.execute(q)
                    dbt.append((time.perf_counter() - t1) * 1000)
                lat.append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        await asyncio.gather(*(client() for _ in range(clients)))
        dt = time.perf_counter() - t0
        await eng.dispose()
        lat.sort(); dbt.sort()
        r = dict(pool=pool, per_s=len(lat) / dt, p50_ms=lat[len(lat) // 2], p99_ms=lat[int(len(lat) * .99)],
                 db_p50_ms=dbt[len(dbt) // 2], db_p99_ms=dbt[int(len(dbt) * .99)])
        rows.append(r)
        print(f"d5 pool={pool:2d} {r['per_s']:6.0f} truy vấn/s  request p50={r['p50_ms']:6.1f} p99={r['p99_ms']:6.1f} ms"
              f"  trong DB p50={r['db_p50_ms']:5.1f} p99={r['db_p99_ms']:5.1f} ms")
    res["d5_pool"] = dict(clients=clients, cores=os.cpu_count(), rows=rows)


# ---------------------------------------------------------------- d8: thời gian giữ kết nối của một POST
async def d8_post_tx(res, n=300):
    """Một transaction POST /v1/invoices đầy đủ (giành idempotency key, cấp số, ghi hóa đơn 12 dòng, lưu kết quả).
    Đo thời gian giữ kết nối — đầu vào S cho định luật Little khi chọn kích thước pool."""
    eng = create_async_engine(DSN, pool_size=2, max_overflow=0)
    async with eng.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
        for stmt in DDL_D3.strip().split(";") + DDL_D2.strip().split(";"):
            if stmt.strip():
                await c.execute(text(stmt))
    S = async_sessionmaker(eng, expire_on_commit=False)
    held = []
    for i in range(n):
        t0 = time.perf_counter()
        async with S() as s, s.begin():
            key = str(uuid.uuid4())
            await s.scalar(text("insert into idempotency_keys(tenant_id,key,request_hash) values (1,:k,'h') "
                                "on conflict (tenant_id,key) do nothing returning key"), {"k": key})
            inv = InvoiceRow(id=i + 1, tenant_id=1, series="1C26TMK", number=0, total=0)
            inv.lines = [LineRow(name=f"Hàng {j}", amount=1000 * j) for j in range(12)]
            s.add(inv)
            await s.flush()
            inv.number = await s.scalar(text(
                "update series_counter set last_number = last_number + 1 where series='1C26TMK' returning last_number"))
            await s.execute(text("update idempotency_keys set invoice_id=:i where tenant_id=1 and key=:k"),
                            {"i": inv.id, "k": key})
        held.append((time.perf_counter() - t0) * 1000)
    held.sort()
    r = dict(n=n, p50_ms=held[n // 2], p90_ms=held[int(n * .9)], p99_ms=held[int(n * .99)], mean_ms=statistics.fmean(held))
    print(f"d8 giữ kết nối mỗi POST: p50={r['p50_ms']:.2f} p90={r['p90_ms']:.2f} p99={r['p99_ms']:.2f} TB={r['mean_ms']:.2f} ms")
    res["d8_post_tx"] = r
    await eng.dispose()


EXPS = dict(d1=d1_nplus1, d2=d2_numbering, d3=d3_idempotency, d4=d4_rls, d4leak=d4_leak, d5=d5_pool,
            d6=d6_lock_queue, d7=d7_outbox, d8=d8_post_tx)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    await ensure_db()
    eng = create_async_engine(DSN, pool_size=40, max_overflow=0)
    out_path = HERE / "results" / "db.json"
    res = json.loads(out_path.read_text()) if out_path.exists() else {}
    for k, f in EXPS.items():
        if a.only and k not in a.only:
            continue
        await (f(res) if k in ("d4leak", "d5", "d6", "d7", "d8") else f(eng, res))
        out_path.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    await eng.dispose()


if __name__ == "__main__":
    asyncio.run(main())
