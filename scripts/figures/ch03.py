"""Hình minh họa cho Module 03 — Pydantic v2: kiến trúc."""
import json
from datetime import datetime
from decimal import Decimal

import numpy as np
from matplotlib.patches import FancyBboxPatch

from figkit import (AQUA, BLUE, GREEN, MAGENTA, ORANGE, RED, VIOLET, YELLOW, arrow, bench, box,
                    canvas, figure, run, tint, vrows, xgrid, ygrid)


# ---------------------------------------------------------------- kiến trúc hai tầng
@figure("architecture", size=(9.4, 4.6))
def _(fig, t):
    ax = canvas(fig, (0, 132), (0, 64))
    cp, cr = t["c"][BLUE], t["c"][ORANGE]
    box(ax, 1, 33, 62, 27, "", t, color=cp, fill=tint(cp, t, .06), radius=1.6)
    ax.text(3, 56.5, "Lúc định nghĩa class — một lần, ~ms (Python)", fontsize=9, weight="bold", color=cp)
    steps = [("class Invoice\n(BaseModel): kiểu,\nField, validator", 3), ("ModelMetaclass\nthu thập FieldInfo", 23),
             ("GenerateSchema\n→ core schema (dict)", 43)]
    for s, x in steps:
        box(ax, x, 38, 18, 13, s, t, color=cp, fill=tint(cp, t, .15), fs=7.8)
    arrow(ax, 21.2, 44.5, 22.8, 44.5, t); arrow(ax, 41.2, 44.5, 42.8, 44.5, t)
    box(ax, 69, 33, 62, 27, "", t, color=cr, fill=tint(cr, t, .06), radius=1.6)
    ax.text(71, 56.5, "pydantic-core (Rust, PyO3)", fontsize=9, weight="bold", color=cr)
    box(ax, 72, 41, 26, 11, "SchemaValidator\n(cây validator)", t, color=cr, fill=tint(cr, t, .18), fs=8.2, weight="bold")
    box(ax, 102, 41, 26, 11, "SchemaSerializer\n(cây serializer)", t, color=cr, fill=tint(cr, t, .18), fs=8.2, weight="bold")
    arrow(ax, 61.2, 44.5, 71.8, 46.5, t, color=t["fg"], lw=1.8)
    ax.text(64, 49, "dựng", fontsize=7.8, color=t["fg2"])
    # đường chạy mỗi request
    ax.text(3, 27.5, "Mỗi request — µs", fontsize=9, weight="bold", color=t["c"][GREEN])
    flow = [("bytes JSON", 3, t["line"]), ("jiter\n(parse Rust)", 25, cr), ("cây validator\n+ validator Python", 49, cr),
            ("Invoice\n(object Python)", 77, t["c"][GREEN]), ("serializer\n→ bytes", 103, cr)]
    for s, x, c in flow:
        box(ax, x, 9, 21, 13, s, t, color=c, fill=tint(c, t, .14), fs=8)
    for x in (24.2, 70.2, 98.2):
        arrow(ax, x, 15.5, x + 0.6 if x != 70.2 else 76.8, 15.5, t)
    arrow(ax, 46.2, 15.5, 48.8, 15.5, t)
    arrow(ax, 85, 40.8, 60, 22.3, t, color=t["muted"], ls=":", lw=1.1)
    arrow(ax, 115, 40.8, 113.5, 22.3, t, color=t["muted"], ls=":", lw=1.1)
    ax.text(49, 4, "lỗi ở bất kỳ nút nào → gom vào một ValidationError", fontsize=8, color=t["c"][RED])


# ---------------------------------------------------------------- cây validator
@figure("validator-tree", size=(9.4, 4.4))
def _(fig, t):
    ax = canvas(fig, (0, 132), (0, 62))
    cr, cp, cy = t["c"][ORANGE], t["c"][MAGENTA], t["c"][BLUE]

    def node(x, y, s, c, w=22, h=6.5, fs=7.6):
        box(ax, x - w / 2, y - h / 2, w, h, s, t, color=c, fill=tint(c, t, .15), fs=fs)

    def edge(x1, y1, x2, y2):
        ax.plot([x1, x2], [y1 - 3.3, y2 + 3.3], color=t["line"], lw=1.1)
    node(66, 56, "Model(Invoice)\n+ model_validator after", cp, w=34)
    node(66, 46, "ModelFields", cr, w=22)
    edge(66, 56, 66, 46)
    kids = [(10, "seller_tax_code\nstr + pattern"), (30, "buyer\nModel(Buyer)"), (50, "issued_at\ndatetime"),
            (72, "lines\nlist(min 1, max 1000)"), (96, "vat… / totals\nint ge=0"), (118, "currency\nliteral")]
    for x, s in kids:
        node(x, 34, s, cr, w=19)
        edge(66, 46, x, 34)
    node(72, 22, "Model(Line)\n(mỗi phần tử)", cp, w=22)
    edge(72, 34, 72, 22)
    leaves = [(36, "line_no\nint ge=1"), (56, "quantity\nfloat gt=0"), (76, "unit_price\nint ge=0"), (96, "vat_rate\nliteral (băm)")]
    for x, s in leaves:
        node(x, 9, s, cr, w=18)
        edge(72, 22, x, 9)
    ax.text(2, 58, "Cây validator của Invoice", fontsize=9.4, weight="bold", color=t["fg"])
    ax.scatter([108], [58], color=cr, s=40); ax.text(110, 58, "chạy trong Rust", fontsize=8, va="center", color=t["fg2"])
    ax.scatter([108], [54], color=cp, s=40); ax.text(110, 54, "có gọi lại Python", fontsize=8, va="center", color=t["fg2"])
    ax.text(2, 1.2, "loc của lỗi = đường đi từ gốc: ('lines', 5, 'quantity')", fontsize=8.2, color=t["fg2"])


# ---------------------------------------------------------------- đường JSON
@figure("json-path", size=(8.6, 3.2))
def _(fig, t):
    ax = fig.subplots()
    pick = [("orjson.loads (chỉ parse)", "schema", t["muted"]), ("json.loads (chỉ parse)", "schema", t["muted"]),
            ("pydantic v2 · model_validate_json", "schema", t["c"][BLUE]),
            ("pydantic v2 · json.loads + model_validate", "schema", t["c"][ORANGE])]
    rows = {r["impl"]: r for r in vrows(level="schema", lines=12)}
    labels = ["orjson.loads\n(chỉ parse)", "json.loads\n(chỉ parse)", "model_validate_json\n(parse + validate)",
              "json.loads +\nmodel_validate"]
    vals = [rows[p[0]]["lo"] for p in pick]
    y = np.arange(len(vals))
    ax.barh(y, vals, color=[p[2] for p in pick], height=0.55)
    for i, v in enumerate(vals):
        ax.text(v + 0.8, i, f"{v:.1f} µs", va="center", fontsize=9, weight="bold", color=t["fg"])
    ax.set_yticks(y, labels, fontsize=8.4); ax.invert_yaxis()
    ax.set_xlim(0, max(vals) * 1.25)
    ax.set_xlabel("µs / hóa đơn 12 dòng (min của 11 lần lặp, 1 core)")
    ax.set_title("Parse + validate thẳng từ JSON tốn ngang chỉ parse bằng json.loads")
    xgrid(ax, t)


# ---------------------------------------------------------------- chi phí dựng schema
@figure("build-cost", size=(8.4, 3.3))
def _(fig, t):
    ax = fig.subplots()
    rows = bench("misc")["schema"]["rows"]
    k = [r["fields"] for r in rows]
    ax.plot(k, [r["build_us"] / 1000 for r in rows], marker="o", color=t["c"][ORANGE], label="định nghĩa class (ms)")
    ax.plot(k, [r["build_defer_us"] / 1000 for r in rows], marker="s", color=t["c"][YELLOW], label="… với defer_build=True (ms)")
    ax.plot(k, [r["validate_us"] / 1000 for r in rows], marker="^", color=t["c"][BLUE], label="validate 1 instance (ms)")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("số trường của model"); ax.set_ylabel("thời gian (ms, thang log)")
    ax.set_title("Dựng validator: ms, một lần — validate: µs, mỗi request")
    for r in rows[::2]:
        ax.annotate(f"×{r['build_us'] / r['validate_us']:.0f}", (r["fields"], r["validate_us"] / 1000),
                    (0, -14), textcoords="offset points", ha="center", fontsize=7.6, color=t["fg2"])
    ax.legend(fontsize=8.2, loc="center right")
    ax.grid(color=t["grid"], lw=0.6); ax.set_axisbelow(True)


# ---------------------------------------------------------------- bảng chuyển đổi (chạy thật lúc vẽ)
def _coerce_table():
    from pydantic import TypeAdapter, ValidationError
    cases = [(int, "42", '"42"'), (int, " 42 ", '" 42 "'), (int, "4_2", '"4_2"'), (int, 42.0, "42.0"),
             (int, 42.5, "42.5"), (int, True, "true"), (int, "1e3", '"1e3"'),
             (bool, "yes", '"yes"'), (bool, 1, "1"), (bool, 2, "2"),
             (str, 42, "42"), (float, "inf", '"inf"'),
             (Decimal, "82.500", '"82.500"'), (datetime, "2026-10-13 11:45", '"2026-10-13 11:45"'),
             (datetime, "2026-10-13", '"2026-10-13"'), (datetime, 1760330700, "1760330700")]
    rows = []
    for tp, py, js in cases:
        ta = TypeAdapter(tp)
        res = []
        for fn, arg, strict in ((ta.validate_python, py, False), (ta.validate_python, py, True),
                                (ta.validate_json, js, False), (ta.validate_json, js, True)):
            try:
                v = fn(arg, strict=strict)
                if isinstance(v, datetime):
                    s = v.strftime("%d/%m %H:%M") + (" UTC" if v.tzinfo else " naive")
                elif isinstance(v, Decimal):
                    s = f"Decimal {v} (= 82,5)"
                else:
                    s = repr(v)
                res.append((True, s))
            except ValidationError:
                res.append((False, "lỗi"))
        rows.append((f"{tp.__name__} ← {js}", res))
    return rows


@figure("coercion", size=(9.4, 6.4))
def _(fig, t):
    ax = fig.subplots()
    rows = _coerce_table()
    cols = ["Python · lax", "Python · strict", "JSON · lax", "JSON · strict"]
    for i, (_, res) in enumerate(rows):
        for j, (ok, s) in enumerate(res):
            c = t["c"][GREEN] if ok else t["muted"]
            warn = ok and (s in ("1", "42") and rows[i][0].startswith("int ← true") or "naive" in s
                           or "82,5" in s or (rows[i][0].startswith("int ← \"4_2\"")))
            if warn:
                c = t["c"][YELLOW]
            ax.add_patch(FancyBboxPatch((j + 0.05, i + 0.08), 0.9, 0.84, boxstyle="round,pad=0,rounding_size=0.08",
                                        fc=tint(c, t, .28), ec=c, lw=0.9))
            ax.text(j + 0.5, i + 0.5, s, ha="center", va="center", fontsize=7.8, color=t["fg"])
    ax.set_xlim(0, 4); ax.set_ylim(len(rows), 0)
    ax.set_xticks(np.arange(4) + 0.5, cols); ax.xaxis.tick_top()
    ax.set_yticks(np.arange(len(rows)) + 0.5, [r[0] for r in rows], fontsize=8)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    ax.set_title("Bảng chuyển đổi chạy thật (Pydantic 2.14) — vàng: được nhận nhưng dễ che lỗi", pad=22, fontsize=9.4)


# ---------------------------------------------------------------- giải phẫu lỗi
@figure("error-anatomy", size=(9.2, 3.8))
def _(fig, t):
    ax = canvas(fig, (0, 128), (0, 52))
    cb, cg = t["c"][BLUE], t["c"][GREEN]
    left = ["type:  'greater_than'", "loc:   ('lines', 0, 'quantity')", "msg:   'Input should be greater than 0'",
            "input: -2", "ctx:   {'gt': 0.0}", "url:   https://errors.pydantic.dev/…"]
    box(ax, 2, 6, 54, 38, "", t, color=cb, fill=tint(cb, t, .08))
    ax.text(4, 40, "Một phần tử của e.errors()", fontsize=8.8, weight="bold", color=cb)
    for i, s in enumerate(left):
        ax.text(4, 34 - i * 5, s, fontsize=8.2, family="monospace", color=t["fg"])
    right = ['"field": "lines.0.quantity"', '"code": "greater_than"', '"message": "Phải lớn hơn 0"']
    box(ax, 72, 14, 54, 28, "", t, color=cg, fill=tint(cg, t, .08))
    ax.text(74, 38, "Problem Details (RFC 9457) · errors[i]", fontsize=8.8, weight="bold", color=cg)
    for i, s in enumerate(right):
        ax.text(74, 31 - i * 5.5, s, fontsize=8.2, family="monospace", color=t["fg"])
    for y1, y2 in ((35, 31.8), (30, 26.3), (15, 21)):
        arrow(ax, 56.5, y1, 71.5, y2, t, color=t["fg2"], lw=1.1)
    ax.text(58, 9.5, "input: KHÔNG trả lại, KHÔNG log\n(có thể là mật khẩu, số thẻ)", fontsize=8, color=t["c"][RED])
    ax.text(2, 48.5, "Dùng type + ctx + loc để dựng thông báo; msg chỉ để người đọc", fontsize=9.2, weight="bold", color=t["fg"])


# ---------------------------------------------------------------- extra
@figure("extra", size=(9.0, 3.2))
def _(fig, t):
    ax = canvas(fig, (0, 126), (0, 44))
    box(ax, 2, 14, 30, 16, 'đầu vào:\n{"unit_price": 1,\n "unitprice": 2}', t, color=t["line"], fs=8.2)
    modes = [("extra='ignore' (mặc định)", "unit_price=1\n«unitprice» âm thầm bị bỏ", AQUA, 34),
             ("extra='forbid'", "422: ('unitprice',)\nextra_forbidden", GREEN, 18),
             ("extra='allow'", "unit_price=1, unitprice=2\nnguy cơ mass assignment", RED, 2)]
    for name, res, c, y in modes:
        col = t["c"][c]
        arrow(ax, 32.3, 22, 49.8, y + 5, t, color=col)
        box(ax, 50, y, 32, 10, name, t, color=col, fill=tint(col, t, .14), fs=8.2, weight="bold")
        ax.text(85, y + 5, res, va="center", fontsize=8, color=t["fg"])
    ax.text(2, 40, "Ba chế độ xử lý trường lạ", fontsize=9.4, weight="bold", color=t["fg"])


# ---------------------------------------------------------------- required/optional
@figure("required", size=(8.4, 3.4))
def _(fig, t):
    ax = canvas(fig, (0, 116), (0, 46))
    hdr = ["khai báo", "bắt buộc?", "nhận null?", "khi không gửi"]
    xs = [2, 44, 66, 88]
    for x, h in zip(xs, hdr):
        ax.text(x, 41, h, fontsize=8.8, weight="bold", color=t["fg"])
    rows = [("x: int", "có", "không", "lỗi missing"), ("x: int = 0", "không", "không", "x = 0"),
            ("x: int | None", "CÓ", "có", "lỗi missing  ← bẫy v1→v2"), ("x: int | None = None", "không", "có", "x = None"),
            ("x: int | None | MISSING = MISSING", "không", "có", "x = MISSING (không dump)")]
    for i, r in enumerate(rows):
        y = 33 - i * 7.2
        trap = "bẫy" in r[3]
        if trap:
            box(ax, 1, y - 2.7, 114, 6.2, "", t, color=t["c"][YELLOW], fill=tint(t["c"][YELLOW], t, .15))
        for x, s in zip(xs, r):
            ax.text(x, y, s, fontsize=8.2, family="monospace" if x == 2 else None, color=t["fg"], va="center")


# ---------------------------------------------------------------- TypeAdapter tái sử dụng
@figure("typeadapter", size=(8.2, 3.0))
def _(fig, t):
    ax = fig.subplots()
    rows = {(r["impl"], r["level"]): r["lo"] for r in vrows(lines=12)}
    cats = ["schema", "full"]
    x = np.arange(2)
    a = [rows[("pydantic v2 · model_validate_json", c)] for c in cats]
    b = [rows[("pydantic v2 · TypeAdapter mỗi request", c)] for c in cats]
    ax.bar(x - 0.18, a, 0.34, color=t["c"][BLUE], label="adapter/model tạo sẵn (cấp module)")
    ax.bar(x + 0.18, b, 0.34, color=t["c"][RED], label="TypeAdapter(list[Invoice]) tạo mỗi request")
    for xi, v in zip(x - 0.18, a):
        ax.text(xi, v + 3, f"{v:.0f}", ha="center", fontsize=8.6, color=t["fg"])
    for xi, v, base in zip(x + 0.18, b, a):
        ax.text(xi, v + 3, f"{v:.0f} (×{v / base:.1f})", ha="center", fontsize=8.6, color=t["fg"], weight="bold")
    ax.set_xticks(x, ["chỉ ràng buộc trường", "+ quy tắc nghiệp vụ Python"])
    ax.set_ylabel("µs / hóa đơn 12 dòng"); ax.set_ylim(0, max(b) * 1.3)
    ax.set_title("Anti-pattern: dựng lại TypeAdapter trong handler")
    ax.legend(fontsize=8.2, loc="upper left")
    ygrid(ax, t)


# ---------------------------------------------------------------- invoice v1 phủ tầng nào
@figure("invoice-v1", size=(8.8, 2.8))
def _(fig, t):
    ax = canvas(fig, (0, 124), (0, 36))
    tiers = [("0 · Vận chuyển", "middleware", t["muted"], "Module 07/11"),
             ("1 · Cú pháp", "jiter (Rust)", t["c"][GREEN], "xong"),
             ("2 · Cấu trúc & trường", "core schema (Rust)", t["c"][GREEN], "xong (InvoiceIn v1)"),
             ("3 · Ngữ nghĩa", "validator Python", t["c"][YELLOW], "Module 04"),
             ("4 · Ngữ cảnh", "dependency + DB", t["muted"], "Module 08/10")]
    for i, (n, w, c, st) in enumerate(tiers):
        x = 2 + i * 24.4
        box(ax, x, 12, 23, 14, f"{n}\n{w}", t, color=c, fill=tint(c, t, .18), fs=7.9)
        ax.text(x + 11.5, 8.5, st, ha="center", fontsize=7.9, color=t["fg2"])
    ax.text(2, 31, "InvoiceIn phiên bản 1 phủ tầng 1–2 hoàn toàn trong Rust; tầng 3 ở Module 04", fontsize=9.2,
            weight="bold", color=t["fg"])


if __name__ == "__main__":
    run("03")
