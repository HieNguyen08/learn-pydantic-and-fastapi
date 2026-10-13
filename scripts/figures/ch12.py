"""Hình minh họa cho Module 12 — Testing & chất lượng (số liệu: scripts/bench/results/testing.json)."""
import numpy as np

from figkit import (AQUA, BLUE, GREEN, MAGENTA, ORANGE, RED, VIOLET, YELLOW, arrow, bench, box,
                    canvas, figure, run, tint, xgrid, ygrid)


def tst():
    return bench("testing")


@figure("pyramid", size=(9.6, 4.2))
def _(fig, t):
    ax = canvas(fig, (0, 136), (0, 60))
    layers = [("end-to-end (staging)", "vài smoke test · giây–phút", RED, 26),
              ("hợp đồng / fuzz", "Schemathesis · giây cho cả API", MAGENTA, 36),
              ("tích hợp + DB", "Postgres thật, savepoint · ~4 ms/test", ORANGE, 46),
              ("tích hợp trong tiến trình", "AsyncClient + ASGITransport\n~0,3–0,5 ms/request", BLUE, 56),
              ("unit + thuộc tính", "hàm thuần, Hypothesis · µs", GREEN, 66)]
    for i, (name, note, c, w) in enumerate(layers):
        y = 46 - i * 9
        col = t["c"][c]
        box(ax, 38 - w / 2, y, w, 8, name, t, color=col, fill=tint(col, t, .18), fs=7.8, weight="bold")
        ax.text(38 + w / 2 + 2, y + 4, note, fontsize=7.4, color=t["fg2"], va="center")
    ax.text(2, 57, "Tầng test cho một API FastAPI — kiểm mỗi quy tắc ở tầng thấp nhất còn có nghĩa", fontsize=9,
            weight="bold", color=t["fg"])
    rows = [("MST, làm tròn thuế, tổng tiền", "unit + thuộc tính"),
            ("422 khi body sai, response_model lọc trường", "trong tiến trình"),
            ("404 cho tenant khác (BOLA), RLS, ràng buộc unique", "tích hợp + DB"),
            ("mọi endpoint khớp OpenAPI, không 5xx", "hợp đồng / fuzz"),
            ("proxy chặn body 4 MiB, TLS, migration", "end-to-end")]
    ax.text(100, 50, "ví dụ quy tắc → tầng", fontsize=8, weight="bold", color=t["fg"])
    for i, (r, l) in enumerate(rows):
        ax.text(100, 45 - i * 8, r, fontsize=7.1, color=t["fg"])
        ax.text(100, 41.6 - i * 8, "→ " + l, fontsize=7.1, color=t["fg2"])


@figure("clients", size=(8.8, 3.2))
def _(fig, t):
    rows = tst()["t1_clients"]
    clients = list(dict.fromkeys(r["client"] for r in rows))
    ax = fig.subplots()
    y = np.arange(len(clients))
    for j, (ep, c) in enumerate((("GET /health", BLUE), ("POST /v1/invoices", ORANGE))):
        v = [next(r["us"] for r in rows if r["client"] == cl and r["endpoint"] == ep) for cl in clients]
        ax.barh(y + (j - 0.5) * 0.38, v, 0.38, color=t["c"][c], label=ep)
        for i, x in enumerate(v):
            ax.text(x + 15, y[i] + (j - 0.5) * 0.38, f"{x:.0f} µs", va="center", fontsize=7.4, color=t["fg2"])
    ax.set_yticks(y, clients, fontsize=7.8)
    ax.invert_yaxis()
    ax.set_xlim(0, 1700)
    ax.set_xlabel("µs mỗi request")
    ax.set_title("Số đo thật (t1): chi phí gọi app trong test")
    ax.legend(fontsize=8, loc="center right")
    xgrid(ax, t)


@figure("db-isolation", size=(9.8, 3.6))
def _(fig, t):
    rows = tst()["t2_db_isolation"]
    gs = fig.add_gridspec(1, 2, width_ratios=[1, 1.15])
    ax = fig.add_subplot(gs[0])
    names = ["tạo lại bảng", "TRUNCATE", "savepoint\nrollback"]
    cols = [t["c"][RED], t["c"][ORANGE], t["c"][GREEN]]
    ax.bar(names, [r["ms_per_test"] for r in rows], color=cols)
    for i, r in enumerate(rows):
        ax.text(i, r["ms_per_test"] + 1.2, f"{r['ms_per_test']:.1f} ms".replace(".", ","), ha="center", fontsize=7.8,
                color=t["fg"])
    ax.set_ylabel("ms mỗi test (12 bảng)")
    ax.set_title("Số đo thật (t2): cô lập DB giữa các test")
    ygrid(ax, t)
    ax2 = fig.add_subplot(gs[1])
    ax2.set_xlim(0, 100); ax2.set_ylim(0, 60); ax2.set_aspect("equal"); ax2.axis("off")
    cg, cb, cv = t["c"][GREEN], t["c"][BLUE], t["c"][VIOLET]
    box(ax2, 2, 4, 96, 48, "", t, color=cv, fill=tint(cv, t, .06))
    ax2.text(4, 48, "fixture: BEGIN (transaction ngoài cùng)", fontsize=7.4, color=cv, weight="bold")
    box(ax2, 8, 18, 84, 24, "", t, color=cb, fill=tint(cb, t, .08))
    ax2.text(10, 38, "code app: session.begin() → SAVEPOINT", fontsize=7.2, color=cb)
    ax2.text(10, 31, "INSERT hóa đơn + 12 dòng, SELECT lại", fontsize=7.2, color=t["fg"])
    ax2.text(10, 24, "session.commit() → RELEASE SAVEPOINT", fontsize=7.2, color=cb)
    ax2.text(4, 9, "fixture: ROLLBACK → DB sạch cho test sau", fontsize=7.4, color=cg, weight="bold")


@figure("pbt", size=(9.6, 3.6))
def _(fig, t):
    ax = canvas(fig, (0, 136), (0, 50))
    cb, cr, cg, co = t["c"][BLUE], t["c"][RED], t["c"][GREEN], t["c"][ORANGE]
    steps = [(2, "strategy\nsinh input", "st.integers(0, 10**12)\nst.sampled_from(rates)", BLUE),
             (30, "chạy thuộc tính", "|tax − exact| ≤ 0,5\nđúng 0,5 → làm tròn lên", VIOLET),
             (58, "phản ví dụ\nđầu tiên", "(…, 10) sau 70 input\n(số lớn, khó đọc)", RED),
             (86, "shrink", "thu nhỏ chuỗi lựa chọn\nngẫu nhiên → input nhỏ hơn", ORANGE),
             (114, "báo cáo", "(525, 10)\n52,5 → 52 ≠ 53", GREEN)]
    for x, h, s, c in steps:
        col = t["c"][c]
        box(ax, x, 18, 22, 20, "", t, color=col, fill=tint(col, t, .1))
        ax.text(x + 11, 34, h, fontsize=8, weight="bold", color=col, ha="center", va="center")
        ax.text(x + 11, 25, s, fontsize=6.7, color=t["fg"], ha="center", va="center")
    for x in (24.3, 52.3, 80.3, 108.3):
        arrow(ax, x, 28, x + 5.4, 28, t, lw=1)
    arrow(ax, 41, 17.7, 13, 17.7, t, color=cg, lw=1, rad=-0.35)
    ax.text(27, 7, "thuộc tính đúng → sinh input tiếp (mặc định 100 lần)", fontsize=7.2, color=cg, ha="center")
    arrow(ax, 104, 38.3, 90, 38.3, t, color=co, lw=1, rad=0.9)
    ax.text(97, 45.5, "lặp tới khi không nhỏ hơn được", fontsize=7.2, color=co, ha="center")
    ax.text(2, 47, "Vòng lặp property-based testing (Hypothesis)", fontsize=9, weight="bold", color=t["fg"])


@figure("pbt-results", size=(9.8, 3.4))
def _(fig, t):
    rows = tst()["t3_property"]
    ax = canvas(fig, (0, 140), (0, 44))
    ax.text(2, 41, "Số đo thật (t3): ba lỗi cài sẵn — test ví dụ và Hypothesis", fontsize=9, weight="bold",
            color=t["fg"])
    hdr = [(2, "lỗi"), (54, "test ví dụ"), (78, "Hypothesis"), (104, "phản ví dụ sau shrink")]
    for x, h in hdr:
        ax.text(x, 34, h, fontsize=7.8, color=t["fg2"], weight="bold")
    for i, r in enumerate(rows):
        y = 25 - i * 9
        ax.text(2, y + 3, r["bug"], fontsize=7.4, color=t["fg"], va="center")
        c = t["c"][RED] if r["example_tests_pass_on_buggy"] else t["c"][GREEN]
        box(ax, 54, y, 22, 6, "qua (bỏ sót)" if r["example_tests_pass_on_buggy"] else "bắt được", t, color=c,
            fill=tint(c, t, .18), fs=7.2)
        c2 = t["c"][GREEN] if r["found"] else t["c"][RED]
        box(ax, 78, y, 24, 6, f"tìm thấy sau {r['examples_to_first_failure']} input", t, color=c2,
            fill=tint(c2, t, .18), fs=7.2)
        ex = r["minimal_example"]
        if isinstance(ex, list):
            ex = "(" + ", ".join(str(v) for v in ex) + ")"
        ex = str(ex).replace("datetime.datetime", "datetime")
        ax.text(104, y + 3, ex, fontsize=7.2, color=t["fg"], va="center", family="monospace")


@figure("fuzz", size=(9.8, 4.0))
def _(fig, t):
    d = tst()["t5_schemathesis"]
    ax = canvas(fig, (0, 140), (0, 56))
    cb, cr, cg, cv, co = (t["c"][k] for k in (BLUE, RED, GREEN, VIOLET, ORANGE))
    box(ax, 2, 34, 22, 12, "FastAPI\n/openapi.json", t, color=cb, fill=tint(cb, t, .14), fs=7.6)
    box(ax, 32, 40, 30, 9, "sinh request HỢP LỆ\n(theo schema)", t, color=cg, fill=tint(cg, t, .12), fs=7.2)
    box(ax, 32, 28, 30, 9, "sinh request SAI\n(vi phạm schema)", t, color=co, fill=tint(co, t, .12), fs=7.2)
    box(ax, 70, 30, 30, 18, "kiểm tra:\nkhông 5xx · response khớp\nschema · status đã khai báo\n· request sai bị 4xx",
        t, color=cv, fill=tint(cv, t, .1), fs=6.9)
    arrow(ax, 24.3, 42, 31.7, 44.5, t, lw=1)
    arrow(ax, 24.3, 38, 31.7, 32.5, t, lw=1)
    arrow(ax, 62.3, 44.5, 69.7, 41, t, lw=1)
    arrow(ax, 62.3, 32.5, 69.7, 36, t, lw=1)
    r = d["buggy"]
    ax.text(104, 47, f"Số đo thật (t5): {r['generated']} test case,\n{r['seconds']:.1f} s".replace(".", ","),
            fontsize=7.6, color=t["fg"], va="top")
    found = [("Server error: tên có dấu → 500", "lỗi 1 (cài sẵn)", cr),
             ("Server error: limit=199 → 500", "lỗi 3: sai response_model (cài sẵn)", cr),
             ("Server error: limit=0 → 500", "lỗi 2, lộ ra sau khi sửa lỗi 3", cr),
             ("Accepted schema-violating request", "\"unit_price\": false → 201 (Pydantic lax)", co),
             ("Undocumented status code", "400 cho body không phải JSON", co),
             ("Invalid Allow header", "405 thiếu phương thức trong Allow", co)]
    for i, (a, b, c) in enumerate(found):
        y = 20 - i * 3.4
        ax.text(2, y, "● " + a, fontsize=7.2, color=c)
        ax.text(60, y, b, fontsize=7.2, color=t["fg2"])
    ax.text(2, 52.5, "Fuzz theo schema: OpenAPI do FastAPI sinh → test tự động", fontsize=9, weight="bold",
            color=t["fg"])


@figure("mutation", size=(9.6, 3.6))
def _(fig, t):
    d = tst()["t4_mutation"]
    s = d["summary"]
    ax1, ax2 = fig.subplots(1, 2, gridspec_kw=dict(width_ratios=[1, 1.4]))
    names = ["điển hình\n(4 assert)", "ví dụ cẩn thận\n(11 assert)", "thuộc tính\n(3 property)"]
    vals = [s["score_typical"] * 100, s["score_examples"] * 100, s["score_properties"] * 100]
    ax1.bar(names, vals, color=[t["c"][RED], t["c"][YELLOW], t["c"][GREEN]])
    for i, v in enumerate(vals):
        ax1.text(i, v + 2, f"{v:.0f}%", ha="center", fontsize=8.2, color=t["fg"])
    ax1.set_ylim(0, 112)
    ax1.set_ylabel("điểm đột biến (%)")
    ax1.set_title(f"{s['mutants']} đột biến (đã loại {s['equivalent']} tương đương)", fontsize=8.8)
    ax1.tick_params(axis="x", labelsize=7.4)
    ygrid(ax1, t)
    rows = [r for r in d["rows"] if not r["likely_equivalent"]]
    surv = [r for r in rows if not r["killed_by_typical"] or not r["killed_by_examples"]]
    ax2.set_xlim(0, 3); ax2.set_ylim(-0.5, len(surv) - 0.5); ax2.invert_yaxis()
    for i, r in enumerate(surv):
        for j, k in enumerate(("killed_by_typical", "killed_by_examples", "killed_by_properties")):
            c = t["c"][GREEN] if r[k] else t["c"][RED]
            ax2.add_patch(__import__("matplotlib.patches", fromlist=["Rectangle"]).Rectangle(
                (j + 0.05, i - 0.4), 0.9, 0.8, color=tint(c, t, .55)))
            ax2.text(j + 0.5, i, "diệt" if r[k] else "SỐNG", ha="center", va="center", fontsize=6.8, color=t["fg"])
    ax2.set_yticks(range(len(surv)), [f"{r['function']}: {r['mutant']}" for r in surv], fontsize=6.8)
    ax2.set_xticks([0.5, 1.5, 2.5], ["điển hình", "ví dụ", "thuộc tính"], fontsize=7.6)
    ax2.tick_params(length=0)
    for sp in ax2.spines.values():
        sp.set_visible(False)
    ax2.set_title("Những đột biến không bị mọi bộ diệt", fontsize=8.8)
    fig.suptitle("Số đo thật (t4): mutation testing trên mst_is_valid, line_tax, invoice_totals", fontsize=9.4,
                 color=t["fg"])
    fig.tight_layout()


@figure("breaking", size=(9.6, 3.6))
def _(fig, t):
    rows = tst()["t6_breaking"]
    ax = canvas(fig, (0, 136), (0, 50))
    ax.text(2, 47, "Số đo thật (t6): diff OpenAPI v1 → v2 do FastAPI sinh", fontsize=9, weight="bold", color=t["fg"])
    for i, r in enumerate(rows):
        y = 38 - i * 5.4
        c = t["c"][RED] if r["kind"] == "BREAKING" else t["c"][GREEN]
        box(ax, 2, y, 20, 4.4, r["kind"], t, color=c, fill=tint(c, t, .2), fs=7)
        ax.text(25, y + 2.2, r["change"], fontsize=7.3, color=t["fg"], va="center")
    ax.text(100, 38.5, "quy tắc theo CHIỀU dữ liệu", fontsize=7.8, weight="bold", color=t["fg"])
    ax.text(100, 34, "request: thêm bắt buộc,\nthu hẹp ràng buộc, bớt enum\n→ breaking", fontsize=7.1,
            color=t["fg2"], va="top")
    ax.text(100, 22, "response: bỏ trường,\nthêm giá trị enum\n→ breaking", fontsize=7.1, color=t["fg2"], va="top")


@figure("ci", size=(9.8, 3.6))
def _(fig, t):
    ax = canvas(fig, (0, 140), (0, 48))
    stages = [("lint + kiểu", "ruff, mypy", "~20 s", GREEN), ("unit + thuộc tính", "Hypothesis ci", "~30 s", GREEN),
              ("tích hợp + DB", "Postgres, savepoint,\nma trận BOLA/BFLA", "~1 phút", BLUE),
              ("đồng thời", "idempotency,\ncấp số", "~20 s", BLUE),
              ("hợp đồng", "diff OpenAPI,\nSchemathesis", "~40 s", VIOLET),
              ("mutation (diff)", "domain/ vừa sửa", "1–3 phút", ORANGE)]
    for i, (h, s, tm, c) in enumerate(stages):
        x = 2 + i * 23
        col = t["c"][c]
        box(ax, x, 18, 21, 18, "", t, color=col, fill=tint(col, t, .1))
        ax.text(x + 10.5, 32.5, h, fontsize=7.6, weight="bold", color=col, ha="center")
        ax.text(x + 10.5, 25.5, s, fontsize=6.8, color=t["fg"], ha="center", va="center")
        ax.text(x + 10.5, 20, tm, fontsize=7, color=t["fg2"], ha="center")
        if i < len(stages) - 1:
            arrow(ax, x + 21.2, 27, x + 22.8, 27, t, lw=1)
    ax.text(2, 44, "Pipeline của invoice-api trên mỗi PR (≈ 4–6 phút); hằng đêm thêm Hypothesis nightly, "
                   "Schemathesis stateful, mutation toàn bộ", fontsize=8.6, weight="bold", color=t["fg"])
    ax.text(2, 10, "Thất bại sớm ở tầng rẻ: lỗi kiểu và quy tắc nghiệp vụ dừng pipeline trước khi bật Postgres",
            fontsize=7.6, color=t["fg2"])


if __name__ == "__main__":
    run("12")
