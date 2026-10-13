"""Hình minh họa cho Module 04 — Validator, kiểu tùy biến & union."""
import random
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

import numpy as np
from matplotlib.patches import FancyBboxPatch

from figkit import (AQUA, BLUE, GREEN, MAGENTA, ORANGE, RED, VIOLET, YELLOW, arrow, bench, box,
                    canvas, figure, run, tint, xgrid, ygrid)


# ---------------------------------------------------------------- củ hành
@figure("onion", size=(9.0, 4.2))
def _(fig, t):
    ax = canvas(fig, (0, 128), (0, 60))
    layers = [("int (lõi, Rust)", 0, t["c"][GREEN]), ("B1 · A1", 1, t["c"][BLUE]), ("W1 (wrap)", 2, t["c"][VIOLET]),
              ("B2 · A2", 3, t["c"][ORANGE])]
    cx, cy = 34, 28
    for name, k, c in reversed(layers):
        w, h = 18 + k * 14, 10 + k * 11
        ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h, boxstyle="round,pad=0,rounding_size=3",
                                    fc=tint(c, t, .12 + 0.04 * (3 - k)), ec=c, lw=1.6))
        ax.text(cx, cy + h / 2 - 3.2, name, ha="center", fontsize=8.4, weight="bold", color=c)
    ax.text(2, 57, "Annotated[int, B1, A1, W1, B2, A2] — mỗi validator bọc mọi thứ bên trái nó", fontsize=9.2,
            weight="bold", color=t["fg"])
    seq = [("B2", ORANGE), ("W1: trước", VIOLET), ("B1", BLUE), ("int", GREEN), ("A1", BLUE), ("W1: sau", VIOLET), ("A2", ORANGE)]
    ax.text(74, 47, "Thứ tự chạy đo được:", fontsize=8.8, weight="bold", color=t["fg"])
    for i, (s, c) in enumerate(seq):
        y = 41 - i * 5.2
        col = t["c"][c]
        box(ax, 76, y - 2, 20, 4.2, s, t, color=col, fill=tint(col, t, .2), fs=8)
        if i < len(seq) - 1:
            arrow(ax, 86, y - 2.2, 86, y - 2.9, t, ms=7)
    ax.text(100, 37, "before: ngoài → trong\n(phải → trái)", fontsize=8, color=t["fg2"])
    ax.text(100, 18, "after: trong → ngoài\n(trái → phải)", fontsize=8, color=t["fg2"])


# ---------------------------------------------------------------- chi phí validator (số đo)
@figure("validator-cost", size=(8.6, 3.4))
def _(fig, t):
    ax = fig.subplots()
    rows = bench("validators")["constraints"][:6]
    names = [r["variant"] for r in rows]
    vals = [r["ns_per_item"] for r in rows]
    base = vals[0]
    cols = [t["muted"], t["c"][GREEN], t["c"][BLUE], t["c"][AQUA], t["c"][ORANGE], t["c"][RED]]
    y = np.arange(len(vals))
    ax.barh(y, vals, color=cols, height=0.58)
    for i, v in enumerate(vals):
        extra = "" if i == 0 else f"  (+{v - base:.0f})"
        ax.text(v + 3, i, f"{v:.0f} ns{extra}", va="center", fontsize=8.6, color=t["fg"])
    ax.set_yticks(y, names, fontsize=8.4); ax.invert_yaxis()
    ax.set_xlim(0, max(vals) * 1.3)
    ax.set_xlabel("ns / phần tử (list 1.000 số thực, min của 9 lần lặp)")
    ax.set_title("Cùng quy tắc «> 0», sáu cách cài")
    xgrid(ax, t)


# ---------------------------------------------------------------- kiểu tùy biến
@figure("custom-type", size=(9.2, 3.6))
def _(fig, t):
    ax = canvas(fig, (0, 130), (0, 50))
    cr, cp, cg = t["c"][ORANGE], t["c"][MAGENTA], t["c"][GREEN]
    box(ax, 2, 22, 22, 11, '"0314409058-002"', t, color=t["line"], fs=8.2)
    box(ax, 30, 22, 30, 11, "str_schema(min 10, max 17)\n(Rust)", t, color=cr, fill=tint(cr, t, .15), fs=8)
    box(ax, 66, 22, 30, 11, "TaxCode._parse\nchuẩn hóa + checksum (Python)", t, color=cp, fill=tint(cp, t, .15), fs=8)
    box(ax, 102, 22, 26, 11, "TaxCode('0314409058002')\nlà str, kiểu riêng", t, color=cg, fill=tint(cg, t, .15), fs=8)
    for x1, x2 in ((24.2, 29.8), (60.2, 65.8), (96.2, 101.8)):
        arrow(ax, x1, 27.5, x2, 27.5, t)
    arrow(ax, 45, 21.8, 45, 12.5, t, color=t["c"][RED]); arrow(ax, 81, 21.8, 81, 12.5, t, color=t["c"][RED])
    ax.text(45, 8.5, "string_too_short /\nstring_too_long", ha="center", fontsize=7.8, color=t["c"][RED])
    ax.text(81, 8.5, "tax_code_format /\ntax_code_checksum {expected}", ha="center", fontsize=7.8, color=t["c"][RED])
    ax.text(102, 44, "__get_pydantic_json_schema__", fontsize=8, weight="bold", color=t["fg"])
    ax.text(102, 40.5, 'pattern ^\\d{10}(-?\\d{3})?$\nexamples, description', fontsize=7.6, color=t["fg2"], va="top")
    ax.text(2, 46, "TaxCode: phần rẻ trong Rust, phần đắt trong Python, lỗi có mã riêng", fontsize=9.2,
            weight="bold", color=t["fg"])


# ---------------------------------------------------------------- làm tròn (mô phỏng)
def _simulate(n_inv=10000, n_lines=12, seed=4):
    rng = random.Random(seed)
    diff_mode, diff_agg = [], []
    for _ in range(n_inv):
        up = even = 0
        exact = Decimal(0)
        for _ in range(n_lines):
            amt = Decimal(rng.randrange(10, 5_000_000, 10))
            rate = Decimal(rng.choice([5, 8, 10]))
            x = amt * rate / 100
            up += int(x.quantize(Decimal(1), ROUND_HALF_UP))
            even += int(x.quantize(Decimal(1), ROUND_HALF_EVEN))
            exact += x
        diff_mode.append(up - even)
        diff_agg.append(up - int(exact.quantize(Decimal(1), ROUND_HALF_UP)))
    return np.array(diff_mode), np.array(diff_agg)


@figure("rounding", size=(8.8, 3.3))
def _(fig, t):
    a1, a2 = fig.subplots(1, 2, gridspec_kw=dict(wspace=0.32))
    dm, da = _simulate()
    vals, cnt = np.unique(dm, return_counts=True)
    a1.bar(vals, cnt / len(dm) * 100, color=t["c"][ORANGE], width=0.6)
    for v, c in zip(vals, cnt):
        a1.text(v, c / len(dm) * 100 + 1.5, f"{c / len(dm) * 100:.1f}%", ha="center", fontsize=8, color=t["fg"])
    a1.set_xlabel("half-up − half-even (đồng, tổng thuế)"); a1.set_ylabel("% hóa đơn")
    a1.set_title("Half-up so với round() của Python")
    a1.set_xticks(vals)
    vals2, cnt2 = np.unique(da, return_counts=True)
    a2.bar(vals2, cnt2 / len(da) * 100, color=t["c"][BLUE], width=0.6)
    a2.set_xlabel("Σ round(dòng) − round(Σ dòng) (đồng)"); a2.set_ylabel("% hóa đơn")
    a2.set_title("Từng dòng so với làm tròn tổng")
    a2.set_xticks(vals2)
    ygrid(a1, t); ygrid(a2, t)
    fig.text(0.01, -0.1, "Mô phỏng 10.000 hóa đơn × 12 dòng, amount ngẫu nhiên bội 10 đồng, thuế suất 5/8/10%.",
             fontsize=7.8, color=t["fg2"])


# ---------------------------------------------------------------- union (số đo)
@figure("union-cost", size=(9.0, 3.4))
def _(fig, t):
    a1, a2 = fig.subplots(1, 2, gridspec_kw=dict(width_ratios=[1, 1.15], wspace=0.42))
    d = bench("validators")
    sc = d["union_scaling"]
    for name, c, lab in (("smart", RED, "smart union"), ("discriminated", GREEN, "discriminator")):
        rr = [r for r in sc if r["variant"] == name]
        a1.plot([r["members"] for r in rr], [r["ns_per_item"] for r in rr], marker="o", color=t["c"][c], label=lab)
    a1.set_xlabel("vị trí của thành viên khớp (k)"); a1.set_ylabel("ns / phần tử")
    a1.set_title("Chi phí theo số thành viên"); a1.set_xticks(range(1, 6))
    a1.legend(fontsize=8); ygrid(a1, t)
    rows = d["unions"]
    names = ["smart", "left_to_right", "discriminator", "Discriminator\n(callable)"]
    vals = [r["ns_per_item"] for r in rows]
    errs = [r["errors_for_one_bad_item"] for r in rows]
    cols = [t["c"][RED], t["c"][ORANGE], t["c"][GREEN], t["c"][AQUA]]
    y = np.arange(4)
    a2.barh(y, vals, color=cols, height=0.55)
    for i, (v, e) in enumerate(zip(vals, errs)):
        a2.text(v + 50, i, f"{v:,.0f} ns · {e} lỗi".replace(",", "."), va="center", fontsize=8.2, color=t["fg"])
    a2.set_yticks(y, names, fontsize=8.2); a2.invert_yaxis(); a2.set_xlim(0, max(vals) * 1.55)
    a2.set_xlabel("ns / phần tử (5 loại thanh toán trộn)")
    a2.set_title("Tốc độ và số lỗi cho 1 phần tử sai")
    xgrid(a2, t)


# ---------------------------------------------------------------- quy trình smart vs discriminated
@figure("union-flow", size=(9.2, 3.8))
def _(fig, t):
    ax = canvas(fig, (0, 130), (0, 54))
    cr, cg = t["c"][RED], t["c"][GREEN]
    ax.text(2, 50, "Smart union", fontsize=9.2, weight="bold", color=cr)
    for i, s in enumerate(["Card?", "Transfer?", "Cash?", "EWallet?", "Voucher?"]):
        box(ax, 2 + i * 12.5, 36, 11, 7, s, t, color=cr, fill=tint(cr, t, .12), fs=7.6)
    ax.text(2, 31, "lượt 1: strict từng thành viên → lượt 2: lax → chọn khớp «tốt nhất»", fontsize=7.8, color=t["fg2"])
    ax.text(2, 27, "thất bại → lỗi của MỌI thành viên", fontsize=7.8, color=cr)
    ax.text(70, 50, "Discriminated union", fontsize=9.2, weight="bold", color=cg)
    box(ax, 70, 36, 18, 7, 'đọc "method"', t, color=cg, fill=tint(cg, t, .15), fs=7.8)
    arrow(ax, 88.3, 39.5, 93.7, 39.5, t, color=cg)
    box(ax, 94, 30, 34, 19, "", t, color=cg, fill=tint(cg, t, .06))
    for i, (k, v) in enumerate([("card", "Card"), ("transfer", "Transfer"), ("cash", "Cash"), ("ewallet", "EWallet")]):
        ax.text(96, 45.5 - i * 3.8, f'"{k}" → {v}', fontsize=7.6, family="monospace", color=t["fg"])
    ax.text(70, 26, "bảng băm O(1) → đúng 1 thành viên → 1 lỗi có loc ('transfer', 'ref')", fontsize=7.8, color=t["fg2"])
    ax.text(70, 22, 'tag lạ → union_tag_invalid, kèm expected_tags', fontsize=7.8, color=t["fg2"])
    box(ax, 2, 3, 126, 13, "", t, color=t["line"], fill=t["panel"])
    ax.text(4, 12, 'OpenAPI: smart → anyOf (client phải tự đoán)  ·  discriminated → oneOf + discriminator.propertyName = "method"',
            fontsize=8, color=t["fg"])
    ax.text(4, 6.5, "→ trình sinh code (TypeScript, Kotlin, Swift) tạo đúng kiểu union có thẻ", fontsize=8, color=t["fg2"])


# ---------------------------------------------------------------- invoice v2: hai vòng lỗi
@figure("invoice-v2", size=(9.2, 3.8))
def _(fig, t):
    ax = canvas(fig, (0, 130), (0, 54))
    cr, cg, co = t["c"][RED], t["c"][GREEN], t["c"][ORANGE]
    ax.text(2, 50, "InvoiceIn v2: lỗi trường trước, lỗi tổng sau", fontsize=9.4, weight="bold", color=t["fg"])
    box(ax, 2, 28, 34, 16, "Lần gửi 1\nMST sai checksum\namount dòng 2 lệch 1đ\ntotal_tax lệch 1đ", t, color=t["line"], fs=7.8)
    box(ax, 44, 28, 40, 16, "422 · 2 lỗi\n(seller_tax_code) tax_code_checksum\n(lines, 1) line_amount", t,
        color=cr, fill=tint(cr, t, .12), fs=7.8)
    ax.text(88, 36, "model validator «after» của InvoiceIn\nKHÔNG chạy vì còn lỗi trường", fontsize=7.8, color=t["fg2"], va="center")
    arrow(ax, 36.3, 36, 43.7, 36, t)
    box(ax, 2, 6, 34, 14, "Lần gửi 2\nđã sửa MST và amount", t, color=t["line"], fs=7.8)
    box(ax, 44, 6, 40, 14, "422 · 1 lỗi\n() invoice_totals\ntotal_tax phải là 7977", t, color=co, fill=tint(co, t, .14), fs=7.8)
    arrow(ax, 36.3, 13, 43.7, 13, t)
    box(ax, 92, 6, 36, 14, "Lần gửi 3 → 201\ntầng 1–3 đều qua", t, color=cg, fill=tint(cg, t, .14), fs=8)
    arrow(ax, 84.3, 13, 91.7, 13, t, color=cg)


if __name__ == "__main__":
    run("04")
