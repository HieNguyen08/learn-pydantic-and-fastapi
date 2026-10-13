"""Hình minh họa cho Module 14 — Capstone (số liệu: scripts/bench/results/capstone.json)."""
import numpy as np

from figkit import (AQUA, BLUE, GREEN, MAGENTA, ORANGE, RED, VIOLET, YELLOW, arrow, bench, box,
                    canvas, figure, run, tint, xgrid, ygrid)


def cap():
    return bench("capstone")


@figure("load", size=(9.4, 3.4))
def _(fig, t):
    """Hồ sơ tải ước lượng theo giờ: 1,8 triệu req/ngày, 85% trong 12 giờ bán hàng, đỉnh trưa/tối ×4."""
    ax = fig.subplots()
    h = np.arange(0, 24, 0.25)
    base = np.where((h >= 8) & (h < 20), 35.0, 0.15 * 1.8e6 / (12 * 3600))   # 15% tải còn lại rải 12 giờ
    peak = 105 * (np.exp(-((h - 12) ** 2) / 0.5) + np.exp(-((h - 18.5) ** 2) / 0.5))
    normal = base + peak
    ax.fill_between(h, normal, color=tint(t["c"][BLUE], t, .35), lw=0)
    ax.plot(h, normal, color=t["c"][BLUE], label="ngày thường (đỉnh ~140 req/s)")
    ax.plot(h, normal * 3, color=t["c"][ORANGE], label="ngày cuối tháng ×3 (đỉnh ~420 req/s)")
    ax.axhline(500, color=t["c"][RED], ls="--", lw=1.2)
    ax.text(23.7, 515, "thiết kế: 500 req/s", fontsize=8, color=t["c"][RED], ha="right")
    ax.axhline(35, color=t["fg2"], ls=":", lw=1)
    ax.text(20.3, 45, "giờ bán ~35 req/s", fontsize=7.4, color=t["fg2"])
    ax.set_xlim(0, 24)
    ax.set_ylim(0, 580)
    ax.set_xticks(range(0, 25, 3))
    ax.set_xlabel("giờ trong ngày")
    ax.set_ylabel("req/s")
    ax.set_title("Ước lượng tải invoice-api theo giờ (giả định của case, minh họa)")
    ax.legend(fontsize=8, loc="upper left", bbox_to_anchor=(0, 0.83))
    ygrid(ax, t)


@figure("datamodel", size=(9.8, 4.4))
def _(fig, t):
    ax = canvas(fig, (0, 140), (0, 62))
    tables = {
        "cap_series": (2, 34, ["tenant_id  PK", "series     PK", "last_number"], VIOLET),
        "invoices": (38, 26, ["id  PK", "tenant_id · series · number", "  UNIQUE(tenant, series, number)",
                              "seller_tax_code, buyer_name", "issued_at  (partition theo tháng)",
                              "total_before_tax, total_tax, total"], BLUE),
        "invoice_lines": (38, 2, ["id  PK · invoice_id  FK", "tenant_id · line_no", "quantity numeric(19,4)",
                                  "unit_price, amount  bigint"], BLUE),
        "idempotency": (92, 34, ["(tenant_id, key)  PK", "request_hash", "status_code, response_body jsonb",
                                 "created_at  (partition theo ngày)"], ORANGE),
        "outbox": (92, 8, ["id  PK · tenant_id", "topic, payload jsonb", "published_at  (NULL = chưa phát)"], GREEN),
    }
    for name, (x, y, cols, c) in tables.items():
        col = t["c"][c]
        h = 5 + 3.6 * len(cols)
        box(ax, x, y, 46 if name in ("invoices", "invoice_lines", "idempotency", "outbox") else 30, h, "", t,
            color=col, fill=tint(col, t, .08))
        ax.text(x + 1.5, y + h - 2.6, name, fontsize=8.2, weight="bold", color=col)
        for i, ctext in enumerate(cols):
            ax.text(x + 1.5, y + h - 6.4 - i * 3.6, ctext, fontsize=6.9, color=t["fg"], family="monospace")
    arrow(ax, 61, 25.7, 61, 20.3, t, lw=1)
    ax.text(62, 22.5, "1 – n", fontsize=7, color=t["fg2"])
    arrow(ax, 32.3, 40, 37.7, 40, t, lw=1, color=t["c"][VIOLET])
    ax.text(2, 28, "cấp số: UPDATE … RETURNING\ncuối transaction (M10 d2)", fontsize=6.9, color=t["c"][VIOLET])
    ax.text(2, 59, "Mô hình dữ liệu invoice-api — mọi bảng có tenant_id + RLS FORCE (WITH CHECK)", fontsize=9,
            weight="bold", color=t["fg"])
    ax.text(92, 30, "cùng transaction với hóa đơn", fontsize=6.9, color=t["fg2"])


@figure("budget", size=(9.4, 3.4))
def _(fig, t):
    rows = {r["part"]: r["us"] for r in cap()["c1_budget"]}
    parts = [("kiểm JWT EdDSA + Principal", "JWT", BLUE), ("GCRA trên Redis (1 round trip)", "GCRA Redis", VIOLET),
             ("validate InvoiceIn (12 dòng, model_validate_json)", "Pydantic", GREEN),
             ("băm model cho idempotency (model_dump_json + sha256)", "hash", AQUA),
             ("transaction Postgres (8 câu lệnh, RLS, commit)", "transaction DB", ORANGE)]
    total = rows["TOÀN BỘ POST /v1/invoices (trong tiến trình)"]
    known = sum(rows[p] for p, _, _ in parts)
    ax = fig.subplots()
    left = 0
    for p, lab, c in parts + [(None, "FastAPI + còn lại", YELLOW)]:
        v = rows[p] if p else total - known
        ax.barh([0], [v / 1000], left=left / 1000, color=t["c"][c], edgecolor=t["bg"])
        if v / total > 0.07:
            ax.text((left + v / 2) / 1000, 0, f"{lab}\n{v / 1000:.2f} ms".replace(".", ","), ha="center", va="center",
                    fontsize=7.4, color="white")
        left += v
    small = ", ".join(f"{lab} {rows[p]:.0f} µs" for p, lab, _ in parts[:4])
    ax.text(0, 0.55, "phần nhỏ: " + small, fontsize=7.6, color=t["fg2"])
    ax.set_yticks([])
    ax.set_ylim(-0.6, 0.8)
    ax.set_xlabel("ms (một request, không tải, trong tiến trình)")
    ax.set_title(f"Số đo thật (c1): ngân sách latency của POST /v1/invoices — tổng {total / 1000:.1f} ms".replace(".", ","))
    xgrid(ax, t)


@figure("capacity", size=(9.8, 3.8))
def _(fig, t):
    rows = cap()["c2_load"]
    ax1, ax2 = fig.subplots(1, 2)
    style = {("sqlalchemy", 1): (RED, "SQLAlchemy, 1 tiến trình"), ("asyncpg", 1): (GREEN, "asyncpg, 1 tiến trình"),
             ("sqlalchemy", 2): (ORANGE, "SQLAlchemy, 2 tiến trình"), ("asyncpg", 2): (BLUE, "asyncpg, 2 tiến trình")}
    for (layer, w), (c, lab) in style.items():
        rr = [r for r in rows if r["layer"] == layer and r["workers"] == w]
        ax1.plot([r["rate"] for r in rr], [r["ok_per_s"] for r in rr], marker="o", color=t["c"][c], label=lab)
        ax2.plot([r["rate"] for r in rr], [r["p99"] for r in rr], marker="o", color=t["c"][c], label=lab)
    ax1.plot([0, 800], [0, 800], color=t["fg2"], ls=":", lw=1)
    ax1.text(700, 740, "y = x", fontsize=7.4, color=t["fg2"], ha="right")
    ax1.set_xlabel("tải gửi tới (req/s)")
    ax1.set_ylabel("201 / s")
    ax1.set_title("Thông lượng")
    ax1.legend(fontsize=7.2, loc="upper left")
    ygrid(ax1, t)
    ax2.axhline(300, color=t["c"][RED], ls="--", lw=1)
    ax2.text(110, 330, "SLO p99 300 ms", fontsize=7.4, color=t["c"][RED])
    ax2.axvline(500, color=t["fg2"], ls=":", lw=1)
    ax2.text(505, 2.2e3, "thiết kế\n500/s", fontsize=7.2, color=t["fg2"], va="top")
    ax2.set_yscale("log")
    ax2.set_xlabel("tải gửi tới (req/s)")
    ax2.set_ylabel("p99 (ms, log)")
    ax2.set_title("p99 của request thành công")
    ygrid(ax2, t)
    fig.suptitle("Số đo thật (c2): invoice-api đầy đủ (JWT, GCRA, Pydantic, RLS, idempotency, outbox) trên uvicorn",
                 fontsize=9.2, color=t["fg"])
    fig.tight_layout()


@figure("db-layer", size=(9.0, 3.4))
def _(fig, t):
    rows = cap()["c3_db_layer_cpu"]
    ax = fig.subplots()
    names = [r["case"].replace("SQLAlchemy text(): ", "SQLAlchemy: ").replace("asyncpg thuần: ", "asyncpg: ") for r in rows]
    y = np.arange(len(rows))
    cols = [t["c"][RED] if "SQLAlchemy" in n else t["c"][GREEN] for n in names]
    ax.barh(y, [r["cpu_ms"] for r in rows], color=cols, label="CPU Python")
    ax.barh(y, [r["wall_ms"] - r["cpu_ms"] for r in rows], left=[r["cpu_ms"] for r in rows],
            color=tint(t["c"][BLUE], t, .35), label="chờ (I/O, Postgres)")
    for i, r in enumerate(rows):
        ax.text(r["wall_ms"] + 0.08, i, f"CPU {r['cpu_ms']:.2f} / tổng {r['wall_ms']:.2f} ms".replace(".", ","),
                va="center", fontsize=7.2, color=t["fg2"])
    ax.set_yticks(y, names, fontsize=7.4)
    ax.invert_yaxis()
    ax.set_xlim(0, 8.5)
    ax.set_xlabel("ms mỗi transaction")
    ax.set_title("Số đo thật (c3): CPU phía Python của cùng một transaction — tầng truy cập DB quyết định")
    ax.legend(fontsize=7.6, loc="lower right")
    xgrid(ax, t)


@figure("aiflow", size=(9.8, 3.8))
def _(fig, t):
    ax = canvas(fig, (0, 140), (0, 52))
    cb, cg, co, cv, cr, cm = (t["c"][k] for k in (BLUE, GREEN, ORANGE, VIOLET, RED, MAGENTA))
    nodes = [(2, 24, "Zendesk\nwebhook", co), (23, 24, "POST /webhooks\nHMAC · Pydantic\n→ 202 (vài ms)", cb),
             (44, 24, "bảng job\nON CONFLICT\n(event_id)", cv), (65, 24, "worker\nSKIP LOCKED\nRAG + LLM", cb),
             (89, 36, "LLM provider\n12 lời gọi đồng thời\n(Little: 0,4/s × 30 s)", cm),
             (89, 8, "Redis pub/sub\ndraft:{ticket}", cv), (116, 24, "SSE → 60 CS\nid · retry ·\nLast-Event-ID", cg)]
    for x, y, s_, c in nodes:
        box(ax, x, y, 19 if x not in (89,) else 22, 12, s_, t, color=c, fill=tint(c, t, .12), fs=6.6)
    for (x1, y1, x2, y2) in ((21.3, 30, 22.7, 30), (42.3, 30, 43.7, 30), (63.3, 30, 64.7, 30),
                             (84.3, 33, 88.7, 40), (88.7, 38, 84.3, 31), (84.3, 27, 88.7, 16),
                             (111.3, 14, 118, 23.7)):
        arrow(ax, x1, y1, x2, y2, t, lw=1)
    ax.text(40, 13, "validate output bằng Pydantic\nsai schema → retry (budget, backoff)\n"
                   "partial JSON → publish từng phần", fontsize=6.9, color=t["fg2"], va="top")
    ax.text(2, 48, "ai-gateway: tách NHẬN việc (webhook < 10 s) khỏi LÀM việc (LLM 5–30 s)", fontsize=9,
            weight="bold", color=t["fg"])
    ax.text(2, 14, "output LLM là dữ liệu chưa tin cậy:\nngười duyệt trước khi gửi khách", fontsize=7, color=cr,
            va="top")


@figure("rollout", size=(9.6, 3.2))
def _(fig, t):
    ax = canvas(fig, (0, 136), (0, 42))
    steps = [("migration\nexpand", "job riêng,\nlock_timeout", VIOLET), ("canary 1%", "tenant nội bộ\n30 phút", ORANGE),
             ("10%", "1 giờ", ORANGE), ("50%", "1 giờ", YELLOW), ("100%", "", GREEN),
             ("contract", "deploy sau,\nkhi không ai dùng", VIOLET)]
    for i, (h, s, c) in enumerate(steps):
        x = 2 + i * 22.5
        col = t["c"][c]
        box(ax, x, 16, 20, 14, "", t, color=col, fill=tint(col, t, .14))
        ax.text(x + 10, 26, h, fontsize=7.8, weight="bold", color=col, ha="center", va="center")
        ax.text(x + 10, 19.5, s, fontsize=6.6, color=t["fg2"], ha="center", va="center")
        if i < len(steps) - 1:
            arrow(ax, x + 20.2, 23, x + 22.3, 23, t, lw=1)
    ax.text(2, 37, "Rollout có cổng SLO: mỗi bậc canary chỉ tiến khi burn rate < 2 và p99 ≤ 1,2 × baseline",
            fontsize=8.8, weight="bold", color=t["fg"])
    ax.text(2, 9, "không đạt → rollback tự động; hành vi mới sau feature flag theo tenant (vd: đường nóng asyncpg)",
            fontsize=7.4, color=t["c"][RED])


@figure("risks", size=(8.6, 4.0))
def _(fig, t):
    ax = fig.subplots()
    risks = [("vượt 500 req/s", 2, 3), ("retry storm", 2, 4), ("lộ chéo tenant", 1, 4), ("trùng/nhảy số", 1, 3),
             ("migration khóa bảng", 2, 3), ("LLM sập/chậm", 3, 2), ("prompt injection", 3, 2),
             ("chi phí telemetry/LLM", 2, 2)]
    for i in range(1, 4):
        for j in range(1, 5):
            sev = i * j
            c = t["c"][GREEN] if sev <= 3 else t["c"][YELLOW] if sev <= 6 else t["c"][RED]
            ax.add_patch(__import__("matplotlib.patches", fromlist=["Rectangle"]).Rectangle(
                (i - 0.5, j - 0.5), 1, 1, color=tint(c, t, .25), lw=0))
    offs = {}
    for name, l, im in risks:
        k = offs.get((l, im), 0)
        offs[(l, im)] = k + 1
        ax.text(l, im + 0.25 - 0.22 * k, name, ha="center", va="center", fontsize=7.6, color=t["fg"])
    ax.set_xlim(0.5, 3.5)
    ax.set_ylim(0.5, 4.5)
    ax.set_xticks([1, 2, 3], ["thấp", "trung bình", "cao"])
    ax.set_yticks([1, 2, 3, 4], ["thấp", "trung bình", "cao", "rất cao"])
    ax.set_xlabel("khả năng xảy ra")
    ax.set_ylabel("tác động")
    ax.set_title("Ma trận rủi ro của hai dịch vụ (mục 12)")
    for s in ax.spines.values():
        s.set_visible(False)


if __name__ == "__main__":
    run("14")
