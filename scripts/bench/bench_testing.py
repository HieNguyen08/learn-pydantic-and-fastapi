"""Thí nghiệm cho Module 12 — Testing & chất lượng → results/testing.json

  t1  chi phí mỗi request: TestClient, httpx.AsyncClient + ASGITransport, uvicorn thật qua TCP
  t2  cô lập DB trong test (PostgreSQL): tạo lại bảng / TRUNCATE / transaction + savepoint rollback
  t3  property-based (Hypothesis) và test ví dụ trên 3 lỗi cài sẵn: tìm được không, sau bao nhiêu ví dụ, ví dụ tối giản
  t4  mutation testing tự viết (đột biến AST): điểm đột biến của bộ test ví dụ và bộ test thuộc tính
  t5  fuzz theo schema bằng Schemathesis trên một app có lỗi cài sẵn
  t6  phát hiện breaking change giữa hai phiên bản OpenAPI do FastAPI sinh
Chạy:  python bench_testing.py [--only t3 t4]     (t2 cần PG_DSN như bench_db.py)
"""
import argparse
import ast
import asyncio
import inspect
import json
import os
import re
import socket
import subprocess
import sys
import textwrap
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "results" / "testing.json"
sys.path.insert(0, str(HERE))


# ---------------------------------------------------------------- t1
def make_app():
    from fastapi import FastAPI
    from pydantic import BaseModel

    class Line(BaseModel):
        name: str
        amount: int

    class Inv(BaseModel):
        buyer: str
        lines: list[Line]

    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.post("/v1/invoices", status_code=201)
    async def create(inv: Inv):
        return {"total": sum(l.amount for l in inv.lines)}
    return app


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def t1_clients(res):
    import httpx
    from fastapi.testclient import TestClient
    app = make_app()
    body = {"buyer": "Cty A", "lines": [{"name": f"Hàng {i}", "amount": 1000 * i} for i in range(12)]}
    N = 2000
    rows = []

    def per_req(fn, n=N):
        fn()
        best = float("inf")
        for _ in range(3):
            t0 = time.perf_counter()
            for _ in range(n):
                fn()
            best = min(best, (time.perf_counter() - t0) / n * 1e6)
        return best

    with TestClient(app) as tc:
        rows.append(dict(client="TestClient", endpoint="GET /health", us=per_req(lambda: tc.get("/health"))))
        rows.append(dict(client="TestClient", endpoint="POST /v1/invoices",
                         us=per_req(lambda: tc.post("/v1/invoices", json=body))))

    async def async_bench(path, method):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            async def one():
                return await (c.get(path) if method == "GET" else c.post(path, json=body))
            await one()
            best = float("inf")
            for _ in range(3):
                t0 = time.perf_counter()
                for _ in range(N):
                    await one()
                best = min(best, (time.perf_counter() - t0) / N * 1e6)
            return best
    rows.append(dict(client="AsyncClient + ASGITransport", endpoint="GET /health",
                     us=asyncio.run(async_bench("/health", "GET"))))
    rows.append(dict(client="AsyncClient + ASGITransport", endpoint="POST /v1/invoices",
                     us=asyncio.run(async_bench("/v1/invoices", "POST"))))

    port = free_port()
    code = "import sys; sys.path.insert(0, %r); from bench_testing import make_app; app = make_app()" % str(HERE)
    (HERE / "_t1_app.py").write_text(code)
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "_t1_app:app", "--port", str(port), "--log-level",
                             "warning", "--loop", "uvloop", "--http", "httptools"], cwd=HERE)
    try:
        for _ in range(100):
            try:
                httpx.get(f"http://127.0.0.1:{port}/health")
                break
            except httpx.HTTPError:
                time.sleep(0.05)
        with httpx.Client(base_url=f"http://127.0.0.1:{port}") as c:
            rows.append(dict(client="uvicorn thật + httpx.Client (TCP)", endpoint="GET /health",
                             us=per_req(lambda: c.get("/health"), 1000)))
            rows.append(dict(client="uvicorn thật + httpx.Client (TCP)", endpoint="POST /v1/invoices",
                             us=per_req(lambda: c.post("/v1/invoices", json=body), 1000)))
    finally:
        proc.terminate()
        proc.wait()
        (HERE / "_t1_app.py").unlink(missing_ok=True)
    for r in rows:
        print(f"t1 {r['client']:36s} {r['endpoint']:18s} {r['us']:7.0f} µs/request")
    res["t1_clients"] = rows


# ---------------------------------------------------------------- t2
def t2_db_isolation(res, n_tests=60):
    from sqlalchemy import ForeignKey, String, func, select, text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
    dsn = os.environ.get("PG_DSN", "postgresql+asyncpg://postgres@/bench?host=/tmp&port=5433")

    class Base(DeclarativeBase):
        pass

    class Inv(Base):
        __tablename__ = "t2_invoices"
        id: Mapped[int] = mapped_column(primary_key=True)
        tenant_id: Mapped[int]
        lines: Mapped[list["Line"]] = relationship()

    class Line(Base):
        __tablename__ = "t2_lines"
        id: Mapped[int] = mapped_column(primary_key=True)
        invoice_id: Mapped[int] = mapped_column(ForeignKey("t2_invoices.id"))
        name: Mapped[str] = mapped_column(String(200))
        amount: Mapped[int]

    for i in range(10):                                  # thêm vài bảng cho giống schema thật (~12 bảng)
        type(f"Extra{i}", (Base,), {"__tablename__": f"t2_extra_{i}", "id": mapped_column(primary_key=True),
                                    "__annotations__": {"id": Mapped[int]}})

    async def body(session: AsyncSession):
        """Thân một test: tạo hóa đơn 12 dòng, đọc lại, kiểm tra."""
        inv = Inv(tenant_id=7, lines=[Line(name=f"Hàng {j}", amount=1000 * j) for j in range(12)])
        session.add(inv)
        await session.flush()
        n = await session.scalar(select(func.count()).select_from(Line).where(Line.invoice_id == inv.id))
        assert n == 12

    async def run():
        eng = create_async_engine(dsn, pool_size=2, max_overflow=0)
        rows = []

        async def recreate():
            async with eng.begin() as c:
                await c.run_sync(Base.metadata.drop_all)
                await c.run_sync(Base.metadata.create_all)
            async with AsyncSession(eng) as s:
                await body(s)
                await s.commit()

        async def truncate():
            async with AsyncSession(eng) as s:
                await body(s)
                await s.commit()
            async with eng.begin() as c:
                await c.execute(text("truncate " + ", ".join(t.name for t in Base.metadata.sorted_tables)
                                     + " restart identity cascade"))

        async def savepoint():
            async with eng.connect() as conn:
                trans = await conn.begin()                               # transaction ngoài cùng của test
                s = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
                await body(s)
                await s.commit()                                         # code app "commit" → chỉ là RELEASE SAVEPOINT
                await s.close()
                await trans.rollback()                                   # dọn sạch: rollback toàn bộ

        async with eng.begin() as c:
            await c.run_sync(Base.metadata.drop_all)
            await c.run_sync(Base.metadata.create_all)
        for name, f in (("tạo lại bảng (drop_all + create_all)", recreate), ("TRUNCATE mọi bảng", truncate),
                        ("transaction + savepoint, rollback", savepoint)):
            await f()
            t0 = time.perf_counter()
            for _ in range(n_tests):
                await f()
            ms = (time.perf_counter() - t0) / n_tests * 1000
            async with eng.connect() as c:
                left = await c.scalar(select(func.count()).select_from(Inv))
            rows.append(dict(strategy=name, ms_per_test=ms, rows_left=left))
            print(f"t2 {name:40s} {ms:7.2f} ms/test   hàng còn lại sau cùng: {left}")
        async with eng.begin() as c:
            await c.run_sync(Base.metadata.drop_all)
        await eng.dispose()
        return rows
    res["t2_db_isolation"] = asyncio.run(run())


# ---------------------------------------------------------------- t3
def t3_property(res):
    from hypothesis import given, settings, HealthCheck, strategies as st
    import testing_subject as S

    out = []

    def run_property(name, prop_factory, max_examples=2000):
        calls = {"n": 0, "first_fail": None, "last_fail": None}
        prop = prop_factory(calls)
        t0 = time.perf_counter()
        try:
            settings(max_examples=max_examples, deadline=None, database=None, derandomize=True,
                     report_multiple_bugs=False, suppress_health_check=list(HealthCheck))(prop)()
            found, minimal = False, None
        except Exception:  # noqa: BLE001
            found, minimal = True, calls["last_fail"]
        dt = (time.perf_counter() - t0) * 1000
        return dict(found=found, examples_to_first_failure=calls["first_fail"], total_calls=calls["n"],
                    minimal_example=minimal, ms=dt)

    def tracked(calls, args, ok):
        calls["n"] += 1
        if not ok:
            if calls["first_fail"] is None:
                calls["first_fail"] = calls["n"]
            calls["last_fail"] = args
        assert ok

    # --- lỗi 1: MST
    examples_mst = ["0100109106", "0312345678"[:9] + "?", "0302024479"]

    def ex_mst(f):
        cases = [("0100109106", True), ("0100109107", False), ("010010910", False), ("01001091AB", False)]
        return all(f(s) == exp for s, exp in cases)

    def prop_mst(calls):
        @given(st.text(alphabet="0123456789", min_size=10, max_size=10))
        def p(s):
            tracked(calls, s, S.mst_is_valid_buggy(s) == S.mst_is_valid(s))
        return p

    # --- lỗi 2: làm tròn thuế
    def ex_tax(f):
        cases = [(100_000, 10, 10_000), (27_500, 8, 2_200), (1_250_000, 5, 62_500), (0, 10, 0)]
        return all(f(a, r) == exp for a, r, exp in cases)

    def prop_tax(calls):
        @given(st.integers(min_value=0, max_value=10**12), st.sampled_from([0, 5, 8, 10]))
        def p(amount, rate):
            # thuộc tính: |thuế - amount·rate/100| ≤ 0,5 và khi phần lẻ đúng bằng 0,5 thì làm tròn LÊN
            exact = __import__("fractions").Fraction(amount * rate, 100)
            got = S.line_tax_buggy(amount, rate)
            ok = abs(got - exact) < __import__("fractions").Fraction(1, 2) or got - exact == __import__("fractions").Fraction(1, 2)
            tracked(calls, (amount, rate), ok)
        return p

    # --- lỗi 3: round-trip
    def ex_rt(model):
        e = model(ticket_id=1, created_at=datetime(2026, 10, 13, 9, 30, 0))
        return model.model_validate_json(e.model_dump_json()) == e

    def prop_rt(calls):
        @given(st.integers(min_value=1, max_value=10**9),
               st.datetimes(timezones=st.sampled_from([None, timezone.utc, timezone(timedelta(hours=7))])))
        def p(tid, dt):
            e = S.EventOutBuggy(ticket_id=tid, created_at=dt)
            try:
                ok = S.EventOutBuggy.model_validate_json(e.model_dump_json()) == e
            except ValueError:                       # ValidationError khi đọc lại cũng là vi phạm round-trip
                ok = False
            tracked(calls, (tid, repr(dt)), ok)
        return p

    bugs = [
        ("MST: so ký tự cuối của chữ số kiểm tra", lambda: ex_mst(S.mst_is_valid_buggy), lambda: ex_mst(S.mst_is_valid),
         prop_mst),
        ("Thuế: round() làm tròn kiểu ngân hàng", lambda: ex_tax(S.line_tax_buggy), lambda: ex_tax(S.line_tax),
         prop_tax),
        ("Round-trip: serializer tự định dạng datetime", lambda: ex_rt(S.EventOutBuggy), lambda: ex_rt(S.EventOut),
         prop_rt),
    ]
    for name, ex_buggy, ex_good, prop in bugs:
        r = run_property(name, prop)
        r.update(bug=name, example_tests_pass_on_buggy=bool(ex_buggy()), example_tests_pass_on_correct=bool(ex_good()))
        out.append(r)
        print(f"t3 {name:44s} test ví dụ {'QUA (bỏ sót)' if r['example_tests_pass_on_buggy'] else 'bắt được'};"
              f" Hypothesis: {'tìm thấy' if r['found'] else 'không thấy'} sau {r['examples_to_first_failure']} ví dụ,"
              f" tối giản → {r['minimal_example']!r} ({r['ms']:.0f} ms)")
    res["t3_property"] = out


# ---------------------------------------------------------------- t4
class Mutator(ast.NodeTransformer):
    """Sinh đột biến: mỗi lần chỉ thay MỘT nút (theo chỉ số target)."""
    SWAP_BIN = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.FloorDiv, ast.Div: ast.Mult, ast.Mod: ast.FloorDiv,
                ast.FloorDiv: ast.Mod}
    SWAP_CMP = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE,
                ast.GtE: ast.Gt, ast.In: ast.NotIn, ast.NotIn: ast.In}

    def __init__(self, target):
        self.target, self.i, self.desc = target, -1, None

    def _hit(self):
        self.i += 1
        return self.i == self.target

    def visit_BinOp(self, node):
        self.generic_visit(node)
        if type(node.op) in self.SWAP_BIN and self._hit():
            self.desc = f"{type(node.op).__name__}→{self.SWAP_BIN[type(node.op)].__name__}"
            node.op = self.SWAP_BIN[type(node.op)]()
        return node

    def visit_Compare(self, node):
        self.generic_visit(node)
        if type(node.ops[0]) in self.SWAP_CMP and self._hit():
            self.desc = f"{type(node.ops[0]).__name__}→{self.SWAP_CMP[type(node.ops[0])].__name__}"
            node.ops[0] = self.SWAP_CMP[type(node.ops[0])]()
        return node

    def visit_Constant(self, node):
        if isinstance(node.value, int) and not isinstance(node.value, bool) and self._hit():
            self.desc = f"hằng {node.value}→{node.value + 1}"
            return ast.copy_location(ast.Constant(node.value + 1), node)
        return node

    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        if isinstance(node.op, ast.Not) and self._hit():
            self.desc = "bỏ not"
            return node.operand
        return node

    def visit_Name(self, node):
        if node.id == "ROUND_HALF_UP" and self._hit():
            self.desc = "HALF_UP→HALF_EVEN"
            return ast.copy_location(ast.Name("ROUND_HALF_EVEN", ast.Load()), node)
        return node

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        if self._hit():
            new = ast.Or() if isinstance(node.op, ast.And) else ast.And()
            self.desc = f"{type(node.op).__name__}→{type(new).__name__}"
            node.op = new
        return node


def t4_mutation(res):
    from hypothesis import given, settings, HealthCheck, strategies as st
    import testing_subject as S

    targets = {"mst_is_valid": S.mst_is_valid, "line_tax": S.line_tax, "invoice_totals": S.invoice_totals}
    oracle_mst = S.mst_is_valid

    def suite_typical(ns):
        """Bộ test 'điển hình': vài ca happy path, như phần lớn codebase."""
        f, g, h = ns["mst_is_valid"], ns["line_tax"], ns["invoice_totals"]
        return (f("0100109106") and not f("123") and g(100_000, 10) == 10_000
                and h([(100_000, 10), (50_000, 0)]) == (150_000, 10_000, 160_000))

    def suite_examples(ns):
        """Bộ test ví dụ 'cẩn thận': sai chữ số kiểm tra, sai độ dài, ký tự lạ, chi nhánh, số lẻ."""
        f, g, h = ns["mst_is_valid"], ns["line_tax"], ns["invoice_totals"]
        return (f("0100109106") and not f("0100109107") and not f("010010910") and not f("01001091AB")
                and f("0100109106001") and not f("0100109106000")
                and g(100_000, 10) == 10_000 and g(27_500, 8) == 2_200 and g(0, 10) == 0
                and h([(27_500, 8), (9_990, 10)]) == (37_490, 3_199, 40_689))

    def suite_properties(ns):
        f, g = ns["mst_is_valid"], ns["line_tax"]
        from fractions import Fraction

        def valid_mst(first9):
            c = 10 - sum(w * int(x) for w, x in zip(S.WEIGHTS, first9)) % 11
            return first9 + str(c) if c < 10 and first9[2:9] != "0000000" else None

        @settings(max_examples=300, deadline=None, database=None, derandomize=True,
                  suppress_health_check=list(HealthCheck))
        @given(st.text(alphabet="0123456789", min_size=9, max_size=9), st.integers(0, 9), st.integers(0, 9))
        def p_mst(first9, pos, digit):
            m = valid_mst(first9)
            if m is None:
                assert not f(first9 + "0")                               # tiền tố không hợp lệ → mọi MST sai
                return
            assert f(m)                                                  # (1) MST hợp lệ được chấp nhận
            mutated = m[:pos] + str(digit) + m[pos + 1:]
            assert f(mutated) == (mutated == m)                          # (2) đổi 1 chữ số → bị phát hiện
            assert not f(m[:9]) and not f(m + "0")                       # (3) sai độ dài
            branch = "%03d" % (pos * 100 + digit * 10 + 1)               # (4) chi nhánh: 001–999 hợp lệ, 000 không
            assert f(m + branch) and not f(m + "000")

        @settings(max_examples=300, deadline=None, database=None, derandomize=True,
                  suppress_health_check=list(HealthCheck))
        @given(st.integers(0, 10**12), st.sampled_from([0, 5, 8, 10]))
        def p_tax(amount, rate):
            exact = Fraction(amount * rate, 100)
            got = g(amount, rate)
            assert -Fraction(1, 2) < got - exact <= Fraction(1, 2)          # gần nhất, nửa → lên
            assert g(amount, rate) >= 0
        @settings(max_examples=200, deadline=None, database=None, derandomize=True,
                  suppress_health_check=list(HealthCheck))
        @given(st.lists(st.tuples(st.integers(0, 10**9), st.sampled_from([0, 5, 8, 10])), max_size=20))
        def p_totals(lines):
            before, tax, total = ns["invoice_totals"](lines)
            assert before == sum(a for a, _ in lines)                        # oracle đơn giản
            assert tax == sum(g(a, r) for a, r in lines)                      # thuế = Σ thuế từng dòng
            assert total == before + tax
        try:
            p_mst()
            p_tax()
            p_totals()
            return True
        except Exception:  # noqa: BLE001
            return False

    module_src = textwrap.dedent(inspect.getsource(S))
    tree0 = ast.parse(module_src)
    rows = []
    killed = {"typical": 0, "examples": 0, "properties": 0}
    total = 0
    for fname in targets:
        fn_node = next(n for n in tree0.body if isinstance(n, ast.FunctionDef) and n.name == fname)
        k = 0
        while True:
            tree = ast.parse(module_src)
            node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == fname)
            m = Mutator(k)
            m.visit(node)
            if m.desc is None:
                break
            ast.fix_missing_locations(tree)
            ns = {}
            try:
                exec(compile(tree, "<mutant>", "exec"), ns)
            except Exception:  # noqa: BLE001
                k += 1
                continue
            res_ex = res_pr = None
            try:
                res_ex = suite_examples(ns)
            except Exception:  # noqa: BLE001
                res_ex = False
            try:
                res_ty = suite_typical(ns)
            except Exception:  # noqa: BLE001
                res_ty = False
            res_pr = suite_properties(ns)
            # mutant tương đương? kiểm bằng so sánh với bản gốc trên nhiều đầu vào
            import random
            rng = random.Random(1)
            if fname == "mst_is_valid":
                samples = ([("%09d%d" % (rng.randrange(10**9), d),) for _ in range(1500) for d in range(10)]
                           + [("0100109106%03d" % b,) for b in range(0, 1000, 7)]
                           + [("12345",), ("01001091AB",), ("01234567890",), ("0100000001",)])
            elif fname == "line_tax":
                samples = [(a, r) for a in range(0, 20001, 7) for r in (0, 5, 8, 10)]
            else:
                samples = [([(rng.randrange(10**7), rng.choice((0, 5, 8, 10))) for _ in range(rng.randrange(6))],)
                           for _ in range(2000)]
            try:
                equiv = all(ns[fname](*a) == targets[fname](*a) for a in samples)
            except Exception:  # noqa: BLE001
                equiv = False
            rows.append(dict(function=fname, mutant=m.desc, killed_by_typical=not res_ty, killed_by_examples=not res_ex,
                             killed_by_properties=not res_pr, likely_equivalent=equiv))
            if not equiv:
                total += 1
                killed["examples"] += int(not res_ex)
                killed["typical"] += int(not res_ty)
                killed["properties"] += int(not res_pr)
            k += 1
    summary = dict(mutants=total, killed_typical=killed["typical"], score_typical=killed["typical"] / total,
                   killed_examples=killed["examples"], killed_properties=killed["properties"],
                   score_examples=killed["examples"] / total, score_properties=killed["properties"] / total,
                   equivalent=sum(r["likely_equivalent"] for r in rows))
    for r in rows:
        print(f"t4 {r['function']:13s} {r['mutant']:18s} điển hình: {'diệt' if r['killed_by_typical'] else 'SỐNG'}  "
              f"ví dụ: {'diệt' if r['killed_by_examples'] else 'SỐNG'}  "
              f"thuộc tính: {'diệt' if r['killed_by_properties'] else 'SỐNG'}"
              f"{'  (tương đương)' if r['likely_equivalent'] else ''}")
    print(f"t4 tổng {total} đột biến (không tính {summary['equivalent']} tương đương): "
          f"điểm bộ điển hình {summary['score_typical']:.0%}, bộ ví dụ cẩn thận {summary['score_examples']:.0%}, "
          f"bộ thuộc tính {summary['score_properties']:.0%}")
    res["t4_mutation"] = dict(rows=rows, summary=summary)


# ---------------------------------------------------------------- t5
FUZZ_APP = '''
from typing import Annotated
from fastapi import FastAPI, Query
from pydantic import BaseModel, Field

app = FastAPI(title="invoice-api (có lỗi cài sẵn)", version="1.0")

class LineIn(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    quantity: Annotated[int, Field(ge=1)]
    unit_price: Annotated[int, Field(ge=0)]

class InvoiceIn(BaseModel):
    buyer_name: Annotated[str, Field(min_length=1, max_length=200)]
    lines: Annotated[list[LineIn], Field(min_length=1, max_length=500)]

class InvoiceOut(BaseModel):
    id: int
    total: int
    average_line: int

@app.post("/v1/invoices", status_code=201, response_model=InvoiceOut)
async def create(inv: InvoiceIn):
    total = sum(l.quantity * l.unit_price for l in inv.lines)
    code = inv.buyer_name.encode("ascii", errors="strict")          # LỖI 1: tên có dấu → 500
    return {"id": 1, "total": total, "average_line": total // len(inv.lines)}

@app.get("/v1/invoices", response_model=list[InvoiceOut])
async def search(limit: Annotated[int, Query(ge=0, le=200)] = 50):
    per_page = 1000 // limit                                          # LỖI 2: limit=0 → ZeroDivisionError
    return [{"id": i, "total": 1000, "average_line": None} for i in range(min(limit, 3))]   # LỖI 3: sai schema
'''


def run_schemathesis(app_src, tag):
    import httpx
    port = free_port()
    (HERE / "_t5_app.py").write_text(app_src)
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "_t5_app:app", "--port", str(port), "--log-level",
                             "critical"], cwd=HERE)
    try:
        for _ in range(100):
            try:
                httpx.get(f"http://127.0.0.1:{port}/openapi.json")
                break
            except httpx.HTTPError:
                time.sleep(0.05)
        st_bin = str(Path(sys.executable).with_name("schemathesis"))
        t0 = time.perf_counter()
        p = subprocess.run([st_bin, "run", f"http://127.0.0.1:{port}/openapi.json", "--checks", "all",
                            "--max-examples", "200", "--seed", "7", "--no-color", "--continue-on-failure"],
                           capture_output=True, text=True, cwd=HERE, env={**os.environ, "NO_COLOR": "1"})
        dt = time.perf_counter() - t0
    finally:
        proc.terminate()
        proc.wait()
        (HERE / "_t5_app.py").unlink(missing_ok=True)
    text_out = (p.stdout + p.stderr).replace(f"127.0.0.1:{port}", "127.0.0.1:8000")
    (HERE / "results" / f"testing_schemathesis_{tag}.txt").write_text(text_out)
    failures = []
    for block in re.split(r"\n_{5,} ", text_out)[1:]:
        op = block.split(" _", 1)[0].strip()
        if op.startswith("SUMMARY") or "=" in op[:3]:
            continue
        for m in re.finditer(r"^- (.+?)$(.*?)curl (.+?)$", block, flags=re.M | re.S):
            failures.append(dict(operation=op, check=m.group(1).strip(), reproduce="curl " + m.group(3).strip()))
    gen = re.search(r"(\d+) generated, (\d+) found (\d+) unique failures", text_out)
    return dict(seconds=dt, exit_code=p.returncode, failures=failures,
                generated=int(gen.group(1)) if gen else None, unique_failures=int(gen.group(3)) if gen else None)


def t5_schemathesis(res):
    out = {}
    out["buggy"] = run_schemathesis(FUZZ_APP, "buggy")
    # sửa lỗi 3 (sai schema response) rồi chạy lại: lỗi 2 (limit=0) mới lộ ra — failure được gom theo chữ ký
    out["fix3"] = run_schemathesis(FUZZ_APP.replace('"average_line": None', '"average_line": 0'), "fix3")
    for k, r in out.items():
        print(f"t5 [{k}] {r['seconds']:.1f} s, {r['generated']} test case, {r['unique_failures']} lỗi khác nhau")
        for f in r["failures"]:
            print(f"     {f['operation']:22s} {f['check']:40s} {f['reproduce'][:110]}")
    res["t5_schemathesis"] = out


# ---------------------------------------------------------------- t6
def openapi_v1_v2():
    from typing import Annotated, Literal
    from fastapi import FastAPI
    from pydantic import BaseModel, Field

    def build(v2: bool):
        class LineIn(BaseModel):
            name: Annotated[str, Field(max_length=100 if v2 else 200)]                     # (c) thu hẹp ràng buộc
            amount: int
            vat_rate: Literal["0", "5", "8", "10"] if v2 else Literal["0", "5", "8", "10", "KCT"]   # (d) bớt enum

        class InvoiceIn(BaseModel):
            buyer_name: str
            lines: list[LineIn]
            if v2:
                buyer_tax_code: str                                                       # (a) thêm trường BẮT BUỘC
                note: str | None = None                                                   # (e) thêm trường tùy chọn

        class InvoiceOut(BaseModel):
            id: int
            total: int
            if not v2:
                issued_at: str                                                            # (b) bỏ trường response
            if v2:
                currency: str = "VND"                                                     # (f) thêm trường response

        app = FastAPI(title="invoice-api", version="2" if v2 else "1")

        @app.post("/v1/invoices", response_model=InvoiceOut, status_code=201)
        async def create(inv: InvoiceIn): ...

        if not v2:
            @app.get("/v1/invoices/{invoice_id}/pdf")                                     # (g) bỏ endpoint
            async def pdf(invoice_id: int): ...
        return app.openapi()
    return build(False), build(True)


def diff_openapi(old, new):
    """Bộ kiểm breaking change tối giản (ý tưởng giống oasdiff/openapi-diff, chỉ vài quy tắc chính)."""
    out = []

    def resolve(spec, sch):
        while "$ref" in sch:
            sch = spec["components"]["schemas"][sch["$ref"].split("/")[-1]]
        return sch

    def walk(o_s, n_s, path, direction):
        o_s, n_s = resolve(old, o_s), resolve(new, n_s)
        if "enum" in o_s and "enum" in n_s:
            removed = set(o_s["enum"]) - set(n_s["enum"])
            added = set(n_s["enum"]) - set(o_s["enum"])
            if direction == "request" and removed:
                out.append(("BREAKING", f"{path}: request bỏ giá trị enum {sorted(removed)}"))
            if direction == "response" and added:
                out.append(("BREAKING", f"{path}: response thêm giá trị enum {sorted(added)} (client cũ không biết)"))
        for k in ("maxLength", "maximum"):
            if k in o_s and k in n_s and n_s[k] < o_s[k] and direction == "request":
                out.append(("BREAKING", f"{path}: request {k} giảm {o_s[k]} → {n_s[k]}"))
        if o_s.get("type") == "array" and n_s.get("type") == "array":
            walk(o_s["items"], n_s["items"], path + "[]", direction)
        op, np_ = o_s.get("properties", {}), n_s.get("properties", {})
        oreq, nreq = set(o_s.get("required", [])), set(n_s.get("required", []))
        for name in op.keys() - np_.keys():
            if direction == "response":
                out.append(("BREAKING", f"{path}.{name}: response bỏ trường"))
            else:
                out.append(("ok", f"{path}.{name}: request bỏ trường (server bỏ qua)"))
        for name in np_.keys() - op.keys():
            if direction == "request" and name in nreq:
                out.append(("BREAKING", f"{path}.{name}: request thêm trường BẮT BUỘC"))
            else:
                out.append(("ok", f"{path}.{name}: thêm trường tùy chọn ({direction})"))
        for name in op.keys() & np_.keys():
            walk(op[name], np_[name], f"{path}.{name}", direction)

    for path, ops in old["paths"].items():
        for method, o in ops.items():
            n = new["paths"].get(path, {}).get(method)
            if n is None:
                out.append(("BREAKING", f"{method.upper()} {path}: endpoint bị xóa"))
                continue
            ob = o.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
            nb = n.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
            if ob and nb:
                walk(ob, nb, f"{method.upper()} {path} body", "request")
            for code, resp in o.get("responses", {}).items():
                orr = resp.get("content", {}).get("application/json", {}).get("schema")
                nr = n.get("responses", {}).get(code, {}).get("content", {}).get("application/json", {}).get("schema")
                if orr and nr:
                    walk(orr, nr, f"{method.upper()} {path} {code}", "response")
    return out


def t6_breaking(res):
    old, new = openapi_v1_v2()
    rows = [dict(kind=k, change=c) for k, c in diff_openapi(old, new)]
    for r in rows:
        print(f"t6 {r['kind']:8s} {r['change']}")
    res["t6_breaking"] = rows



EXPS = dict(t1=t1_clients, t2=t2_db_isolation, t3=t3_property, t4=t4_mutation, t5=t5_schemathesis,
            t6=t6_breaking)

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
