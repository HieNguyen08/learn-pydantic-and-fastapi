"""Hình minh họa cho Module 10 — Database & persistence (số liệu: scripts/bench/results/db.json)."""
import math

import numpy as np

from figkit import (AQUA, BLUE, GREEN, MAGENTA, ORANGE, RED, VIOLET, YELLOW, arrow, bench, box,
                    canvas, figure, run, tint, xgrid, ygrid)


def db():
    return bench("db")


@figure("layers", size=(9.4, 3.6))
def _(fig, t):
    ax = canvas(fig, (0, 134), (0, 50))
    cb, co, cg, cv = t["c"][BLUE], t["c"][ORANGE], t["c"][GREEN], t["c"][VIOLET]
    box(ax, 2, 20, 22, 12, "JSON\nrequest", t, color=t["line"], fs=8)
    box(ax, 30, 18, 26, 16, "InvoiceIn\n(Pydantic)\nkiểu + quy tắc\nnghiệp vụ", t, color=cb, fill=tint(cb, t, .15), fs=7.8)
    box(ax, 62, 18, 26, 16, "Invoice (ORM)\nbảng, quan hệ,\ntenant_id, signed_xml", t, color=co, fill=tint(co, t, .15), fs=7.8)
    box(ax, 94, 18, 26, 16, "InvoiceOut\n(Pydantic)\nfrom_attributes\nchỉ trường công khai", t, color=cg, fill=tint(cg, t, .15), fs=7.8)
    box(ax, 62, 2, 26, 9, "PostgreSQL", t, color=cv, fill=tint(cv, t, .15), fs=8.2)
    arrow(ax, 24.3, 26, 29.7, 26, t)
    arrow(ax, 56.3, 26, 61.7, 26, t)
    arrow(ax, 88.3, 26, 93.7, 26, t)
    arrow(ax, 72, 17.7, 72, 11.3, t, color=cv)
    arrow(ax, 78, 11.3, 78, 17.7, t, color=cv)
    ax.text(43, 38, "validate (M04)", fontsize=7.6, color=cb, ha="center")
    ax.text(75, 38, "repository: nạp đủ\n(selectinload) rồi mới đưa ra", fontsize=7.4, color=co, ha="center")
    ax.text(107, 38, "lọc trường (M07)", fontsize=7.6, color=cg, ha="center")
    ax.text(121, 26, "→ JSON", fontsize=8, color=t["fg2"], va="center")
    ax.text(2, 47, "Ba biểu diễn của một hóa đơn — mỗi cái tiến hóa với tốc độ riêng", fontsize=9.2, weight="bold", color=t["fg"])
    ax.text(92, 6.5, "cột nội bộ không bao giờ đi qua\nInvoiceOut (chống lộ dữ liệu, M11)", fontsize=7.4, color=t["fg2"], va="center")


@figure("session", size=(10.0, 3.9))
def _(fig, t):
    ax = canvas(fig, (0, 160), (0, 58))
    lanes = [("client", 46), ("FastAPI\n(get_session)", 34), ("handler", 22), ("pool / Postgres", 10)]
    for name, y in lanes:
        ax.text(2, y, name, fontsize=8, color=t["fg2"], va="center")
        ax.plot([22, 158], [y, y], color=t["grid"], lw=1, zorder=0)
    cb, cg, cr, cv = t["c"][BLUE], t["c"][GREEN], t["c"][RED], t["c"][VIOLET]
    steps = [
        (24, 46, 34, "POST", t["fg2"]),
        (34, 34, 10, "mượn kết nối\nBEGIN; SET LOCAL\napp.tenant_id", cv),
        (56, 34, 22, "yield session", cb),
        (76, 22, 10, "INSERT … flush()\n(lấy id)", cb),
        (98, 22, 34, "return\nInvoiceOut", cb),
        (116, 34, 10, "COMMIT\ntrả kết nối", cg),
        (138, 34, 46, "201\nCreated", cg),
    ]
    for x, y1, y2, s, c in steps:
        arrow(ax, x, y1, x + 6, y2, t, color=c, lw=1.3)
        ax.text(x + 6.8, (y1 + y2) / 2 + 1.5, s, fontsize=7.2, color=c, va="center")
    ax.add_patch(__import__("matplotlib.patches", fromlist=["Rectangle"]).Rectangle(
        (40, 6.5), 82, 7, facecolor=tint(cv, t, .12), edgecolor="none", zorder=0))
    ax.text(81, 3.5, "transaction mở — kết nối bị giữ (~6,6 ms với POST hóa đơn, d8)", fontsize=7.4, color=cv, ha="center")
    ax.text(2, 55, "Session-per-request với Depends(get_session, scope=\"function\")", fontsize=9.2, weight="bold", color=t["fg"])
    ax.text(2, 51, "ngoại lệ ở bất kỳ đâu trong handler → ROLLBACK, không có 201", fontsize=7.6, color=cr)


@figure("pool", size=(9.4, 3.8))
def _(fig, t):
    ax = canvas(fig, (0, 134), (0, 52))
    cb, cg, cr, co = t["c"][BLUE], t["c"][GREEN], t["c"][RED], t["c"][ORANGE]
    ax.text(2, 48, "QueuePool(pool_size=5, max_overflow=0, pool_timeout=2)", fontsize=9, weight="bold",
            color=t["fg"], family="monospace")
    for i in range(6):
        box(ax, 4 + i * 7, 26, 6, 6, "", t, color=co, fill=tint(co, t, .25))
    ax.text(4, 36, "request chờ mượn (hàng đợi FIFO)", fontsize=7.6, color=co)
    arrow(ax, 47, 29, 55, 29, t, color=co)
    box(ax, 56, 10, 40, 32, "", t, color=cb, fill=tint(cb, t, .06))
    ax.text(58, 38.5, "pool", fontsize=8.2, color=cb, weight="bold")
    for i in range(5):
        busy = i < 4
        c = cr if busy else cg
        box(ax, 59, 33 - i * 5, 34, 4, ("kết nối %d: đang dùng" % (i + 1)) if busy else "kết nối 5: rảnh", t,
            color=c, fill=tint(c, t, .15), fs=7.2)
    for i in range(5):
        arrow(ax, 93.3, 35 - i * 5, 103.7, 26, t, lw=0.8, color=t["line"])
    box(ax, 104, 18, 28, 16, "PostgreSQL\nmỗi kết nối =\n1 tiến trình backend", t, color=t["c"][VIOLET],
        fill=tint(t["c"][VIOLET], t, .15), fs=7.8)
    ax.text(4, 20, "chờ quá pool_timeout →\nTimeoutError: QueuePool limit\nof size … reached", fontsize=7.4, color=cr, va="top")
    ax.text(56, 6, "commit/rollback → kết nối quay về pool (không đóng)", fontsize=7.4, color=t["fg2"])


def erlang_c(a, c):
    s = sum(a ** k / math.factorial(k) for k in range(c))
    top = a ** c / math.factorial(c) * c / (c - a)
    return top / (s + top)


@figure("little", size=(8.6, 3.4))
def _(fig, t):
    S = db()["d8_post_tx"]["mean_ms"] / 1000
    ax = fig.subplots()
    lam = np.linspace(10, 1400, 400)
    for c, col in ((4, RED), (6, ORANGE), (8, BLUE), (10, GREEN), (16, VIOLET)):
        a = lam * S
        p = [erlang_c(x, c) * 100 if x < c else np.nan for x in a]
        ax.plot(lam, p, color=t["c"][col], label=f"pool = {c}")
    ax.axvline(500, color=t["fg2"], ls="--", lw=1)
    ax.text(510, 50, "tải thiết kế\n500 req/s", fontsize=7.6, color=t["fg2"], va="top")
    ax.set_xlabel("transaction/s (λ)")
    ax.set_ylabel("P(phải chờ pool) %")
    ax.set_title(f"Erlang C với thời gian giữ kết nối đo được S = {S * 1000:.1f} ms (d8)".replace(".", ","))
    ax.set_ylim(0, 100)
    ax.legend(fontsize=8, loc="lower right")
    ygrid(ax, t)


@figure("pool-size", size=(9.6, 3.6))
def _(fig, t):
    d = db()["d5_pool"]
    rows = d["rows"]
    pools = [r["pool"] for r in rows]
    x = np.arange(len(pools))
    ax1, ax2 = fig.subplots(1, 2)
    ax1.bar(x, [r["per_s"] for r in rows], color=[t["c"][GREEN] if p == 8 else t["c"][BLUE] for p in pools])
    ax1.set_xticks(x, pools)
    ax1.set_xlabel("pool_size")
    ax1.set_ylabel("truy vấn/s")
    ax1.set_title(f"Thông lượng — đỉnh ở 2 × {d['cores']} core")
    for i, r in enumerate(rows):
        ax1.text(i, r["per_s"] + 3, f"{r['per_s']:.0f}", ha="center", fontsize=7.4, color=t["fg2"])
    ygrid(ax1, t)
    wait = [r["p50_ms"] - r["db_p50_ms"] for r in rows]
    indb = [r["db_p50_ms"] for r in rows]
    ax2.bar(x, wait, color=t["c"][ORANGE], label="chờ trong app (pool)")
    ax2.bar(x, indb, bottom=wait, color=t["c"][VIOLET], label="chạy trong DB")
    ax2.set_xticks(x, pools)
    ax2.set_xlabel("pool_size")
    ax2.set_ylabel("ms (p50)")
    ax2.set_title("Latency p50: hàng đợi chỉ đổi chỗ")
    ax2.legend(fontsize=7.6, loc="upper right")
    ygrid(ax2, t)
    fig.suptitle("Số đo thật (d5): 64 client, truy vấn tốn CPU, Postgres 16 trên 4 vCPU", fontsize=9.4, color=t["fg"])
    fig.tight_layout()


@figure("nplus1", size=(9.4, 3.4))
def _(fig, t):
    rows = db()["d1_nplus1"]
    ax1, ax2 = fig.subplots(1, 2)
    col = {"N+1": RED, "selectinload": GREEN, "joinedload": BLUE}
    for s, c in col.items():
        rr = [r for r in rows if r["strategy"] == s]
        ax1.plot([r["invoices"] for r in rr], [r["ms"] for r in rr], marker="o", color=t["c"][c], label=s)
    ax1.set_xlabel("số hóa đơn (mỗi HĐ 12 dòng)")
    ax1.set_ylabel("ms")
    ax1.set_title("Thời gian nạp danh sách")
    ax1.legend(fontsize=8)
    ygrid(ax1, t)
    n200 = [r for r in rows if r["invoices"] == 200]
    names = [r["strategy"] for r in n200]
    ax2.barh(names, [r["queries"] for r in n200], color=[t["c"][col[n]] for n in names])
    for i, r in enumerate(n200):
        ax2.text(r["queries"] + 3, i, f"{r['queries']} truy vấn · {r['ms']:.1f} ms".replace(".", ","), va="center", fontsize=7.6,
                 color=t["fg2"])
    ax2.set_xlim(0, 300)
    ax2.set_xlabel("số truy vấn (200 hóa đơn)")
    ax2.set_title("Số round trip")
    ax2.invert_yaxis()
    xgrid(ax2, t)
    fig.suptitle("Số đo thật (d1): PostgreSQL 16 + asyncpg, Unix socket", fontsize=9.4, color=t["fg"])
    fig.tight_layout()


@figure("numbering", size=(9.6, 3.8))
def _(fig, t):
    rows = db()["d2_numbering"]
    ax1, ax2 = fig.subplots(1, 2, gridspec_kw=dict(width_ratios=[1.25, 1]))
    labels = ["MAX()+1", "khóa hàng\n(UPDATE…RETURNING)", "sequence", "sequence\n+5% rollback"]
    x = np.arange(len(rows))
    ax1.bar(x - 0.2, [r["duplicates"] for r in rows], 0.4, color=t["c"][RED], label="số bị trùng")
    ax1.bar(x + 0.2, [r["gaps"] for r in rows], 0.4, color=t["c"][ORANGE], label="khoảng trống")
    for i, r in enumerate(rows):
        ax1.text(i - 0.2, r["duplicates"] + 6, str(r["duplicates"]), ha="center", fontsize=7.6, color=t["fg2"])
        ax1.text(i + 0.2, r["gaps"] + 6, str(r["gaps"]), ha="center", fontsize=7.6, color=t["fg2"])
    ax1.set_xticks(x, labels, fontsize=7.4)
    ax1.set_ylabel(f"trên {rows[0]['requests']} giao dịch")
    ax1.set_title("Đúng đắn: chỉ khóa hàng đạt cả hai")
    ax1.legend(fontsize=7.6)
    ygrid(ax1, t)
    cols = [t["c"][RED], t["c"][GREEN], t["c"][ORANGE], t["c"][ORANGE]]
    ax2.barh(x, [r["per_s"] for r in rows], color=cols)
    ax2.set_yticks(x, labels, fontsize=7.4)
    ax2.invert_yaxis()
    for i, r in enumerate(rows):
        ax2.text(r["per_s"] + 15, i, f"{r['per_s']:.0f}/s", va="center", fontsize=7.6, color=t["fg2"])
    ax2.set_xlim(0, 1400)
    ax2.set_xlabel("giao dịch/s (32 đồng thời)")
    ax2.set_title("Cái giá: tuần tự hóa theo ký hiệu")
    xgrid(ax2, t)
    fig.suptitle("Số đo thật (d2): cấp số hóa đơn cho cùng một ký hiệu", fontsize=9.4, color=t["fg"])
    fig.tight_layout()


@figure("idem", size=(9.8, 4.2))
def _(fig, t):
    rows = db()["d3_idempotency"]
    gs = fig.add_gridspec(1, 2, width_ratios=[1.15, 1])
    ax = fig.add_subplot(gs[0])
    ax.set_xlim(0, 105); ax.set_ylim(0, 60); ax.set_aspect("equal"); ax.axis("off")
    cr, cg = t["c"][RED], t["c"][GREEN]
    ax.text(0, 57, "Kiểm tra rồi ghi: cả hai đều thấy \"chưa có\"", fontsize=8.4, weight="bold", color=cr)
    for i, (lab, y) in enumerate((("request A", 48), ("request B", 40))):
        ax.text(0, y, lab, fontsize=7.6, color=t["fg2"], va="center")
        box(ax, 16, y - 3, 26, 6, "SELECT key: rỗng", t, color=cr, fill=tint(cr, t, .12), fs=6.8)
        box(ax, 44, y - 3, 18, 6, "xử lý 2 ms", t, color=t["line"], fs=6.8)
        box(ax, 64, y - 3, 30, 6, "INSERT hóa đơn", t, color=cr, fill=tint(cr, t, .12), fs=6.8)
    ax.text(0, 32, "→ không unique: 2 hóa đơn · có unique: B rollback, trả 500", fontsize=7.2, color=cr)
    ax.text(0, 24, "Giành khóa trước: ON CONFLICT DO NOTHING", fontsize=8.4, weight="bold", color=cg)
    box(ax, 16, 13, 26, 6, "giành khóa: OK", t, color=cg, fill=tint(cg, t, .12), fs=6.6)
    box(ax, 44, 13, 26, 6, "xử lý + lưu response", t, color=t["line"], fs=6.6)
    box(ax, 72, 13, 14, 6, "COMMIT", t, color=cg, fill=tint(cg, t, .2), fs=6.8)
    ax.text(0, 16, "request A", fontsize=7.6, color=t["fg2"], va="center")
    ax.text(0, 6, "request B", fontsize=7.6, color=t["fg2"], va="center")
    box(ax, 16, 3, 70, 6, "INSERT key … CHỜ transaction A kết thúc", t, color=t["c"][ORANGE],
        fill=tint(t["c"][ORANGE], t, .12), fs=6.8)
    box(ax, 88, 2, 16, 8, "xung đột →\nphát lại 201", t, color=cg, fill=tint(cg, t, .12), fs=6.4)
    ax2 = fig.add_subplot(gs[1])
    names = ["SELECT→INSERT\nkhông unique", "SELECT→INSERT\ncó PRIMARY KEY", "ON CONFLICT\ntrước"]
    keys = [("created", "tạo mới", RED), ("error", "lỗi 500", ORANGE), ("replay", "phát lại", GREEN)]
    left = np.zeros(len(rows))
    for k, lab, c in keys:
        v = np.array([r["outcomes"].get(k, 0) for r in rows])
        ax2.barh(names, v, left=left, color=t["c"][c], label=lab)
        left += v
    for i, r in enumerate(rows):
        ax2.text(51, i, f"{r['invoices_per_key']:.1f} HĐ".replace(".", ","), va="center", fontsize=7.6, color=t["fg"])
    ax2.set_xlim(0, 62)
    ax2.set_xlabel(f"kết cục của {rows[0]['duplicates_per_trial']} request cùng khóa (TB {rows[0]['trials']} lần)")
    ax2.invert_yaxis()
    ax2.tick_params(axis="y", labelsize=7.4)
    ax2.legend(fontsize=7.4, loc="lower right", ncols=3, bbox_to_anchor=(1.0, -0.42))
    ax2.set_title("Số đo thật (d3)")
    xgrid(ax2, t)
    fig.tight_layout()


@figure("rls", size=(9.4, 3.8))
def _(fig, t):
    d = db()["d4_rls"]
    ax = canvas(fig, (0, 134), (0, 52))
    cb, co, cg, cv = t["c"][BLUE], t["c"][ORANGE], t["c"][GREEN], t["c"][VIOLET]
    ax.text(2, 48, "Cùng một câu  SELECT count(*) FROM invoices  — không có WHERE", fontsize=9, weight="bold", color=t["fg"])
    for i, (r, c) in enumerate(zip(d, (cb, co))):
        y = 30 - i * 16
        box(ax, 2, y, 30, 11, f"request tenant {r['tenant']}\nset_config('app.tenant_id',\n'{r['tenant']}', true)", t,
            color=c, fill=tint(c, t, .14), fs=7.2)
        arrow(ax, 32.3, y + 5.5, 43.7, 22, t, color=c)
        arrow(ax, 84.3, 22, 95.7, y + 5.5, t, color=c)
        box(ax, 96, y, 36, 11, f"thấy {r['rows_visible']} hàng\ntenant_id = {r['tenants_seen']}", t, color=c,
            fill=tint(c, t, .14), fs=7.6)
    box(ax, 44, 12, 40, 20, "", t, color=cv, fill=tint(cv, t, .08))
    ax.text(64, 28, "policy tenant_isolation", fontsize=7.8, color=cv, ha="center", weight="bold")
    ax.text(64, 22, "USING (tenant_id =\ncurrent_setting('app.tenant_id')::int)", fontsize=6.9, color=t["fg"],
            ha="center", va="center", family="monospace")
    ax.text(64, 15, "bảng: 30 hàng, 3 tenant", fontsize=7.2, color=t["fg2"], ha="center")
    ax.text(2, 4, "Bẫy: SET (cấp session) sống cùng kết nối → request sau dùng lại kết nối từ pool thấy tenant cũ (d4leak).\n"
                  "SET LOCAL hết hạn ở COMMIT → request quên đặt tenant thì lỗi, không lộ dữ liệu.", fontsize=7.4,
            color=t["c"][RED], va="center")


@figure("lockqueue", size=(9.6, 3.8))
def _(fig, t):
    rows = db()["d6_lock_queue"]
    ax = fig.subplots()
    for r, c in zip(rows, (RED, GREEN)):
        tt = [p["t"] for p in r["reads"]]
        ms = [p["ms"] for p in r["reads"]]
        ax.plot(tt, ms, marker="o", ms=3.5, color=t["c"][c], label=r["case"])
    ax.axvspan(0, 2.0, color=t["c"][VIOLET], alpha=0.10)
    ax.text(1.98, 1900, "transaction báo cáo giữ ACCESS SHARE (0 → 2 s)", fontsize=7.6, color=t["c"][VIOLET],
            ha="right", va="top")
    ax.axvline(0.2, color=t["fg2"], ls="--", lw=1)
    ax.text(0.23, 700, "0,2 s: ALTER TABLE xếp hàng\nchờ ACCESS EXCLUSIVE", fontsize=7.6, color=t["fg2"], va="top")
    ax.set_ylim(-60, 2000)
    ax.set_xlabel("thời điểm request API gửi SELECT (s)")
    ax.set_ylabel("latency SELECT (ms)")
    ax.set_title("Số đo thật (d6): DDL chờ khóa chặn mọi truy vấn đến sau nó")
    ax.legend(fontsize=8, loc="center right")
    ygrid(ax, t)


@figure("expand", size=(9.8, 3.8))
def _(fig, t):
    ax = canvas(fig, (0, 140), (0, 52))
    steps = [("1. Expand", "ADD COLUMN\nlegal_name NULL", "DB", VIOLET),
             ("2. Dual write", "app ghi cả hai,\nđọc cột cũ", "app v2", BLUE),
             ("3. Backfill", "UPDATE theo lô\n1.000 hàng", "DB", VIOLET),
             ("4. Chuyển đọc", "đọc legal_name,\nvẫn ghi cả hai", "app v3", BLUE),
             ("5. Ngừng ghi cũ", "chỉ legal_name", "app v4", BLUE),
             ("6. Contract", "NOT NULL,\nDROP buyer_name", "DB", RED)]
    for i, (h, s, who, c) in enumerate(steps):
        x = 2 + i * 23
        col = t["c"][c]
        box(ax, x, 22, 21, 16, "", t, color=col, fill=tint(col, t, .12))
        ax.text(x + 10.5, 34.5, h, fontsize=7.8, weight="bold", color=col, ha="center")
        ax.text(x + 10.5, 27.5, s, fontsize=7, color=t["fg"], ha="center", va="center")
        ax.text(x + 10.5, 18.5, who, fontsize=7.2, color=t["fg2"], ha="center")
        if i < len(steps) - 1:
            arrow(ax, x + 21.2, 30, x + 22.8, 30, t, lw=1)
    ax.add_patch(__import__("matplotlib.patches", fromlist=["Rectangle"]).Rectangle(
        (2, 9), 113, 4, facecolor=tint(t["c"][GREEN], t, .25), edgecolor="none"))
    ax.text(58, 11, "cột cũ buyer_name còn tồn tại → rollback app luôn an toàn", fontsize=7.4, color=t["c"][GREEN],
            ha="center", va="center")
    ax.text(2, 48, "Expand/contract: mỗi bước tương thích với cả phiên bản app trước và sau nó", fontsize=9.2,
            weight="bold", color=t["fg"])
    ax.text(2, 4, "Mọi DDL: SET LOCAL lock_timeout · index: CREATE INDEX CONCURRENTLY · ràng buộc: NOT VALID rồi VALIDATE",
            fontsize=7.4, color=t["fg2"])


@figure("outbox", size=(9.6, 4.0))
def _(fig, t):
    ax = canvas(fig, (0, 136), (0, 56))
    cr, cg, cb, cv, co = t["c"][RED], t["c"][GREEN], t["c"][BLUE], t["c"][VIOLET], t["c"][ORANGE]
    ax.text(2, 52, "Dual write (sai)", fontsize=8.8, weight="bold", color=cr)
    box(ax, 2, 36, 20, 9, "handler", t, color=t["line"], fs=7.8)
    box(ax, 32, 40, 22, 7, "COMMIT DB", t, color=cv, fill=tint(cv, t, .12), fs=7.4)
    box(ax, 32, 30, 22, 7, "publish broker", t, color=co, fill=tint(co, t, .12), fs=7.4)
    arrow(ax, 22.3, 41, 31.7, 43.5, t, lw=1)
    arrow(ax, 22.3, 39, 31.7, 33.5, t, lw=1)
    ax.text(56, 38.5, "✗ chết ở giữa\n→ mất / thừa\nsự kiện", fontsize=7.4, color=cr, va="center")
    ax.text(72, 52, "Transactional outbox", fontsize=8.8, weight="bold", color=cg)
    box(ax, 72, 26, 30, 21, "", t, color=cv, fill=tint(cv, t, .07))
    ax.text(87, 44, "MỘT transaction", fontsize=7.4, color=cv, ha="center")
    box(ax, 74, 35, 26, 6, "INSERT invoices", t, color=cv, fs=7.2)
    box(ax, 74, 28, 26, 6, "INSERT outbox", t, color=cg, fill=tint(cg, t, .15), fs=7.2)
    box(ax, 72, 8, 30, 10, "relay\nSELECT … FOR UPDATE\nSKIP LOCKED", t, color=cb, fill=tint(cb, t, .12), fs=7)
    arrow(ax, 87, 25.7, 87, 18.3, t, color=cb)
    box(ax, 110, 8, 24, 10, "broker\n(Kafka/NATS)", t, color=co, fill=tint(co, t, .12), fs=7.4)
    arrow(ax, 102.3, 13, 109.7, 13, t, color=co)
    box(ax, 110, 30, 24, 12, "consumer\nidempotent\n(event_id)", t, color=cg, fill=tint(cg, t, .12), fs=7.2)
    arrow(ax, 122, 18.3, 122, 29.7, t, color=co)
    ax.text(2, 18, "Hóa đơn và sự kiện cùng commit hoặc cùng biến mất.\nRelay có thể gửi lại sau khi chết → at-least-once;\n"
                   "người tiêu thụ phải khử trùng bằng event_id (như idempotency key).", fontsize=7.6, color=t["fg2"],
            va="top")


@figure("outbox-scale", size=(8.4, 3.2))
def _(fig, t):
    rows = db()["d7_outbox"]
    ax = fig.subplots()
    for lock, c in (("FOR UPDATE (không SKIP LOCKED)", RED), ("FOR UPDATE SKIP LOCKED", GREEN)):
        rr = [r for r in rows if r["lock"] == lock]
        ax.plot([r["relays"] for r in rr], [r["events_per_s"] / 1000 for r in rr], marker="o", color=t["c"][c],
                label=lock)
        dy = 1.2 if c == GREEN else -2.2
        for r in rr:
            ax.text(r["relays"] - 0.05, r["events_per_s"] / 1000 + dy, f"{r['events_per_s'] / 1000:.1f}k".replace(".", ","),
                    fontsize=7.4, color=t["c"][c], ha="right")
    ax.set_xticks([1, 2, 4])
    ax.set_xlabel("số relay song song")
    ax.set_ylabel("nghìn sự kiện/s")
    ax.set_title("Số đo thật (d7): relay outbox, lô 100, gửi broker 5 ms/lô — 0 sự kiện trùng")
    ax.set_ylim(6, 40)
    ax.legend(fontsize=8, loc="upper left")
    ygrid(ax, t)


if __name__ == "__main__":
    run("10")
