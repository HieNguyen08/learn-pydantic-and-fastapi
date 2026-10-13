"""Hình minh họa cho Module 06 — Hiệu năng Pydantic."""
import numpy as np

from figkit import (AQUA, BLUE, GREEN, MAGENTA, ORANGE, RED, VIOLET, YELLOW, arrow, bench, box,
                    canvas, figure, run, tint, vrows, xgrid, ygrid)

LIBS = [("pydantic v2 · model_validate_json", "Pydantic v2", BLUE),
        ("msgspec · Struct", "msgspec", GREEN),
        ("dataclasses + code tay", "dataclasses tay", AQUA),
        ("attrs + cattrs", "attrs + cattrs", VIOLET),
        ("pydantic v1 · parse_raw", "Pydantic v1", ORANGE),
        ("marshmallow 4", "marshmallow 4", RED)]


@figure("noise", size=(8.0, 3.0))
def _(fig, t):
    ax = fig.subplots()
    rows = bench("breakdown")["noise"]
    x = np.arange(1, len(rows) + 1)
    ax.vlines(x, [r["min"] for r in rows], [r["max"] for r in rows], color=t["line"], lw=2)
    ax.scatter(x, [r["min"] for r in rows], color=t["c"][GREEN], zorder=3, label="min của 11 lần lặp")
    ax.scatter(x, [r["median"] for r in rows], color=t["c"][ORANGE], zorder=3, label="trung vị")
    ax.scatter(x, [r["max"] for r in rows], color=t["muted"], zorder=3, s=14, label="max")
    ax.set_xticks(x, [f"tiến trình {i}" for i in x], fontsize=7.6)
    ax.set_ylabel("µs / hóa đơn 12 dòng"); ax.set_ylim(0, 45)
    ax.set_title("Cùng một phép đo, 8 tiến trình: dao động ±15% giữa các lần chạy")
    ax.legend(fontsize=7.8, ncol=3, loc="lower right")
    ygrid(ax, t)


@figure("libs-12", size=(8.8, 3.8))
def _(fig, t):
    ax = fig.subplots()
    r = {(x["impl"], x["level"]): x["lo"] for x in vrows(lines=12)}
    names = [("orjson.loads (chỉ parse)", "orjson (chỉ parse)", t["muted"]),
             ("json.loads (chỉ parse)", "json.loads (chỉ parse)", t["muted"])] + [(a, b, t["c"][c]) for a, b, c in LIBS]
    y = np.arange(len(names))
    for i, (k, lab, c) in enumerate(names):
        s = r.get((k, "schema")); f = r.get((k, "full"))
        ax.barh(i - 0.18, s, 0.34, color=tint(c, t, .55))
        if f:
            ax.barh(i + 0.18, f, 0.34, color=c)
            ax.text(f * 1.08, i + 0.18, f"{f:.0f}", va="center", fontsize=7.8, color=t["fg"])
        ax.text(s * 1.08, i - 0.18, f"{s:.0f}", va="center", fontsize=7.8, color=t["fg2"])
    ax.set_xscale("log"); ax.set_xlim(5, 1500)
    ax.set_yticks(y, [n[1] for n in names], fontsize=8.4); ax.invert_yaxis()
    ax.set_xlabel("µs / hóa đơn 12 dòng (thang log, min) — nhạt: schema, đậm: full")
    ax.set_title("Số đo thật: chín cách validate cùng một hóa đơn")
    xgrid(ax, t)


@figure("scaling", size=(8.4, 3.6))
def _(fig, t):
    ax = fig.subplots()
    rows = vrows(level="full")
    for k, lab, c in LIBS:
        rr = sorted([x for x in rows if x["impl"] == k], key=lambda x: x["lines"])
        ax.plot([x["lines"] for x in rr], [x["lo"] for x in rr], marker="o", color=t["c"][c], label=lab)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("số dòng hàng"); ax.set_ylabel("µs / hóa đơn (min, mức full)")
    ax.set_title("Mọi thư viện tuyến tính theo kích thước; khoảng cách là tỷ lệ hằng số")
    ax.legend(fontsize=7.8, loc="upper left", ncol=2)
    ax.grid(color=t["grid"], lw=0.6); ax.set_axisbelow(True)


@figure("cost-model", size=(8.8, 3.3))
def _(fig, t):
    a1, a2 = fig.subplots(1, 2, gridspec_kw=dict(wspace=0.55))
    rows = vrows(level="full")
    items = LIBS + [("pydantic v2 · TypeAdapter mỗi request", "v2 + TypeAdapter/request", MAGENTA)]
    A, B, labs, cols = [], [], [], []
    for k, lab, c in items:
        rr = sorted([x for x in rows if x["impl"] == k], key=lambda x: x["lines"])
        b, a = np.polyfit([x["lines"] for x in rr], [x["lo"] for x in rr], 1)
        A.append(a); B.append(b); labs.append(lab); cols.append(t["c"][c])
    y = np.arange(len(items))
    a1.barh(y, A, color=cols, height=0.6); a2.barh(y, B, color=cols, height=0.6)
    for i in y:
        a1.text(A[i] + 2, i, f"{A[i]:.1f}", va="center", fontsize=7.8, color=t["fg"])
        a2.text(B[i] + 0.4, i, f"{B[i]:.2f}", va="center", fontsize=7.8, color=t["fg"])
    for a in (a1, a2):
        a.set_yticks(y, labs, fontsize=7.8); a.invert_yaxis(); xgrid(a, t)
    a2.set_yticks(y, [""] * len(y))
    a1.set_title("a: chi phí cố định (µs)"); a2.set_title("b: mỗi dòng hàng (µs)")
    a1.set_xlim(0, 140); a2.set_xlim(0, 36)
    fig.suptitle("Mô hình t(n) = a + b·n khớp trên 4 kích thước (mức full)", fontsize=9.6, x=0.02, ha="left",
                 weight="bold", color=t["fg"], y=1.04)


@figure("breakdown", size=(8.4, 3.2))
def _(fig, t):
    ax = fig.subplots()
    rows = bench("breakdown")["breakdown"]
    labels = [f"{r['lines']} dòng" for r in rows]
    parse = np.array([r["parse_us"] for r in rows])
    struct = np.array([r["schema_us"] for r in rows]) - parse
    rules = np.array([r["full_us"] - r["schema_us"] for r in rows])
    ser = np.array([r["ser_us"] for r in rows])
    tot = parse + struct + rules + ser
    parts = [(parse, "parse JSON", VIOLET), (struct, "validate cấu trúc (Rust)", BLUE),
             (rules, "quy tắc Python của bạn", ORANGE), (ser, "serialize response", GREEN)]
    left = np.zeros(len(rows))
    y = np.arange(len(rows))
    for v, lab, c in parts:
        ax.barh(y, v / tot * 100, left=left, color=t["c"][c], label=lab, height=0.55)
        for i in range(len(rows)):
            if v[i] / tot[i] > 0.08:
                ax.text(left[i] + v[i] / tot[i] * 50, i, f"{v[i]:.0f}", ha="center", va="center", fontsize=7.6, color="white")
        left += v / tot * 100
    for i in range(len(rows)):
        ax.text(101, i, f"Σ {tot[i]:.0f} µs", va="center", fontsize=8, color=t["fg"])
    ax.set_yticks(y, labels); ax.invert_yaxis(); ax.set_xlim(0, 118)
    ax.set_xlabel("% thời gian Pydantic cho một hóa đơn (số trong ô: µs)")
    ax.set_title("Phân rã chi phí Pydantic: parse → cấu trúc → quy tắc → serialize")
    ax.legend(fontsize=7.6, ncol=4, loc="upper center", bbox_to_anchor=(0.45, -0.25))


@figure("amdahl", size=(8.0, 3.4))
def _(fig, t):
    ax = fig.subplots()
    p = np.linspace(0, 1, 300)
    for s, c in ((2, BLUE), (10, AQUA), (np.inf, VIOLET)):
        S = 1 / ((1 - p) + (p / s if np.isfinite(s) else 0)) if np.isfinite(s) else 1 / np.clip(1 - p, 1e-3, None)
        ax.plot(p * 100, S, color=t["c"][c], label=f"phần đó nhanh {('vô hạn' if not np.isfinite(s) else f'{s}×')}")
    for pp, lab, ty in ((0.17, "invoice-api (h11): p ≈ 17%", 3.4), (0.32, "invoice-api ([standard]): p ≈ 32%", 2.6)):
        S = 1 / ((1 - pp) + pp / 2)
        ax.scatter([pp * 100], [S], color=t["c"][RED], zorder=3)
        ax.annotate(f"{lab}\nmsgspec ~2× → S = {S:.2f}×", (pp * 100, S), (22, ty), fontsize=7.8,
                    color=t["fg"], arrowprops=dict(arrowstyle="->", color=t["fg2"]))
    ax.axhline(1.7, color=t["c"][GREEN], ls=":", lw=1.3)
    ax.axhline(1.25, color=t["c"][ORANGE], ls=":", lw=1.3)
    ax.text(60, 1.31, "tự model_validate_json ([standard]): ~1,25×", fontsize=7.8, color=t["c"][ORANGE])
    ax.text(60, 1.78, "đổi sang uvicorn[standard]: ~1,7× (đo thật)", fontsize=7.8, color=t["c"][GREEN])
    ax.set_xlim(0, 100); ax.set_ylim(1, 5)
    ax.set_xlabel("p: % thời gian request dành cho validation"); ax.set_ylabel("tăng tốc cả request S")
    ax.set_title("Định luật Amdahl: tối ưu phần nhỏ chỉ cho lợi ích nhỏ")
    ax.legend(fontsize=7.8, loc="upper left")
    ygrid(ax, t)


@figure("checklist", size=(8.2, 3.0))
def _(fig, t):
    ax = fig.subplots()
    r = {(x["impl"], x["level"]): x["lo"] for x in vrows(lines=12)}
    v = bench("validators")
    un = {x["variant"]: x["ns_per_item"] for x in v["unions"]}
    ser = {(x["case"], x["lines"]): x["us"] for x in bench("misc")["ser"]}
    items = [("model_validate_json thay\njson.loads + model_validate",
              r[("pydantic v2 · json.loads + model_validate", "schema")] / r[("pydantic v2 · model_validate_json", "schema")]),
             ("TypeAdapter ở cấp module\n(hóa đơn 12 dòng)",
              r[("pydantic v2 · TypeAdapter mỗi request", "schema")] / r[("pydantic v2 · model_validate_json", "schema")]),
             ("discriminated thay\nsmart union", un["smart union (mặc định)"] / un["discriminator='method'"]),
             ("model_dump_json thay\nmodel_dump + json.dumps",
              ser[("model_dump() + json.dumps", 12)] / ser[("model_dump_json()", 12)])]
    y = np.arange(len(items))
    ax.barh(y, [i[1] for i in items], color=t["c"][GREEN], height=0.55)
    for i, (_, s) in enumerate(items):
        ax.text(s + 0.08, i, f"{s:.1f}×", va="center", fontsize=8.6, weight="bold", color=t["fg"])
    ax.set_yticks(y, [i[0] for i in items], fontsize=8); ax.invert_yaxis()
    ax.set_xlabel("nhanh hơn bao nhiêu lần cho phần liên quan (số đo thật)"); ax.set_xlim(0, 6)
    ax.set_title("Bốn tối ưu mặc định, không rủi ro")
    xgrid(ax, t)


@figure("batch", size=(9.0, 3.6))
def _(fig, t):
    ax = canvas(fig, (0, 128), (0, 50))
    cr, cb, cg = t["c"][RED], t["c"][BLUE], t["c"][GREEN]
    ax.text(2, 46.5, "Một worker async, batch 500 hóa đơn × 200 dòng", fontsize=9, weight="bold", color=cr)
    box(ax, 2, 32, 88, 8, "validate batch ~190 ms CPU — event loop không làm gì khác", t, color=cr, fill=tint(cr, t, .2), fs=8)
    for i, x in enumerate((10, 30, 55, 75)):
        ax.annotate("", xy=(x, 31.5), xytext=(x, 26), arrowprops=dict(arrowstyle="-|>", color=cb))
        ax.text(x, 24, f"req {i + 1}", ha="center", fontsize=7.4, color=cb)
    box(ax, 92, 32, 34, 8, "req 1–4 chạy SAU\n(trễ thêm tới 190 ms)", t, color=cb, fill=tint(cb, t, .12), fs=7.6)
    ax.text(2, 18, "Thiết kế của invoice-api: giới hạn 10.000 dòng + 202 Accepted + worker riêng", fontsize=9,
            weight="bold", color=cg)
    box(ax, 2, 4, 30, 9, "API: kiểm tra kích thước\n→ ghi hàng đợi → 202", t, color=cg, fill=tint(cg, t, .14), fs=7.8)
    arrow(ax, 32.3, 8.5, 41.7, 8.5, t)
    box(ax, 42, 4, 34, 9, "worker (tiến trình riêng):\nvalidate + ghi từng hóa đơn", t, color=cg, fill=tint(cg, t, .14), fs=7.8)
    arrow(ax, 76.3, 8.5, 85.7, 8.5, t)
    box(ax, 86, 4, 40, 9, "GET /v1/invoice-batches/{id}\n→ kết quả từng hóa đơn", t, color=cg, fill=tint(cg, t, .14), fs=7.8)


if __name__ == "__main__":
    run("06")
