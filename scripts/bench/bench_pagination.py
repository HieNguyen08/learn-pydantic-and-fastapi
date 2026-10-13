"""Phân trang offset vs cursor (keyset) trên SQLite 1 triệu hóa đơn (Module 02).

Chạy:  python bench_pagination.py → results/pagination.json
"""
import json
import random
import sqlite3
import statistics
import time
from pathlib import Path

HERE = Path(__file__).parent
N, PAGE = 1_000_000, 50


def main():
    db = HERE / "results" / "pagination.sqlite"
    db.unlink(missing_ok=True)
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE invoices (id INTEGER PRIMARY KEY, tenant_id INT, issued_at INT, total INT)")
    rng = random.Random(1)
    t = 1_700_000_000
    rows = []
    for i in range(1, N + 1):
        t += rng.randint(0, 3)
        rows.append((i, 1, t, rng.randint(10_000, 5_000_000)))
    con.executemany("INSERT INTO invoices VALUES (?,?,?,?)", rows)
    con.execute("CREATE INDEX ix_tenant_issued ON invoices(tenant_id, issued_at DESC, id DESC)")
    con.commit()
    out = []
    for page in (1, 10, 100, 1000, 5000, 10000, 19000):
        off = (page - 1) * PAGE
        q_off = "SELECT id, issued_at, total FROM invoices WHERE tenant_id=1 ORDER BY issued_at DESC, id DESC LIMIT ? OFFSET ?"
        # mốc cursor = phần tử cuối của trang trước
        if off:
            last = con.execute("SELECT issued_at, id FROM invoices WHERE tenant_id=1 ORDER BY issued_at DESC, id DESC LIMIT 1 OFFSET ?", (off - 1,)).fetchone()
        q_cur = ("SELECT id, issued_at, total FROM invoices WHERE tenant_id=1 AND (issued_at, id) < (?, ?) "
                 "ORDER BY issued_at DESC, id DESC LIMIT ?")

        def run_off():
            return con.execute(q_off, (PAGE, off)).fetchall()

        def run_cur():
            if not off:
                return con.execute(q_off, (PAGE, 0)).fetchall()
            return con.execute(q_cur, (last[0], last[1], PAGE)).fetchall()
        assert run_off() == run_cur()
        to = [time_it(run_off) for _ in range(7)]
        tc = [time_it(run_cur) for _ in range(7)]
        out.append(dict(page=page, offset_ms=statistics.median(to), cursor_ms=statistics.median(tc)))
        print(out[-1])
    con.close()
    db.unlink(missing_ok=True)
    (HERE / "results" / "pagination.json").write_text(json.dumps(out, indent=1))


def time_it(f):
    t0 = time.perf_counter(); f(); return (time.perf_counter() - t0) * 1000


if __name__ == "__main__":
    main()
