"""Hình minh họa cho Module 01 — Kiểu dữ liệu & validation."""
import numpy as np
from matplotlib.patches import Ellipse

from figkit import (AQUA, BLUE, GREEN, MAGENTA, ORANGE, RED, VIOLET, YELLOW, arrow, box,
                    canvas, figure, note, run, tint, xgrid, ygrid)


# ---------------------------------------------------------------- phổ các cách gõ kiểu
@figure("spectrum", size=(8.8, 3.8))
def _(fig, t):
    ax = canvas(fig, (0, 124), (0, 54))
    ax.annotate("", xy=(121, 8), xytext=(4, 8), arrowprops=dict(arrowstyle="-|>", color=t["fg2"], lw=1.4))
    ax.text(62, 3.2, "đảm bảo lúc chạy tăng dần  →  chi phí kiểm tra lúc chạy tăng dần", ha="center", fontsize=8.8, color=t["fg2"])
    items = [
        (4, "Python không hint", "không đảm bảo\nchi phí 0", t["muted"]),
        (28, "Hint + mypy/pyright", "đúng bên trong code\nhint bị xóa: chi phí 0\nmù với dữ liệu ngoài", t["c"][VIOLET]),
        (52, "Hint + Pydantic\nở ranh giới", "cast có kiểm tra\nĐÚNG MỘT LẦN ở ranh giới\n~30 µs/hóa đơn", t["c"][BLUE]),
        (76, "Transient\n(Reticulated Python)", "kiểm tra nông\nở mọi biên hàm", t["c"][AQUA]),
        (100, "Sound gradual\n(Typed Racket)", "cast + proxy ở mọi biên\nmột số cấu hình chậm\n>100× (Takikawa 2016)", t["c"][ORANGE]),
    ]
    for x, title, body, c in items:
        hl = "Pydantic" in title
        box(ax, x, 26, 21, 13, title, t, color=c, fill=tint(c, t, .22 if hl else .12), fs=8.6, weight="bold",
            lw=2.4 if hl else 1.3)
        ax.text(x + 10.5, 23.5, body, ha="center", va="top", fontsize=7.8, color=t["fg2"], linespacing=1.4)
        ax.plot([x + 10.5], [8], marker="o", color=c, ms=7)
    ax.text(2, 49.5, "Các điểm trên phổ gõ kiểu: Python + Pydantic đặt cast có kiểm tra tại ranh giới thay vì ở mọi nơi",
            fontsize=9.4, weight="bold", color=t["fg"])
    ax.text(2, 44.5, "(vị trí trên trục là định tính; con số lấy từ Module 06 và Takikawa et al. 2016)", fontsize=7.8, color=t["muted"])


# ---------------------------------------------------------------- bằng chứng thực nghiệm
@figure("evidence", size=(8.8, 3.2))
def _(fig, t):
    a1, a2 = fig.subplots(1, 2, gridspec_kw=dict(width_ratios=[1.2, 1], wspace=0.38))
    labs = ["Flow\n(JS, Gao 2017)", "TypeScript\n(JS, Gao 2017)", "mypy\n(Python, Khan 2021)"]
    vals = [15, 15, 15]
    cols = [t["c"][ORANGE], t["c"][BLUE], t["c"][VIOLET]]
    a1.bar(range(3), vals, color=cols, width=0.55)
    a1.bar(range(3), [85] * 3, bottom=vals, color=tint(t["muted"], t, .25), width=0.55)
    for i in range(3):
        a1.text(i, 7, "~15%", ha="center", fontsize=9, color="white", weight="bold")
        a1.text(i, 55, "lỗi khác\n(logic, tích hợp,\ndữ liệu ngoài)", ha="center", fontsize=7.2, color=t["fg2"])
    a1.set_xticks(range(3), labs, fontsize=7.8); a1.set_ylim(0, 100)
    a1.set_ylabel("% lỗi đã sửa trong dự án công khai")
    a1.set_title("Type checker bắt được bao nhiêu lỗi?")
    yrs, pct = [2015, 2021], [3.8, 10.9]
    a2.plot(yrs, pct, color=t["c"][VIOLET], ls="--", marker="o", ms=8)
    for x, y in zip(yrs, pct):
        a2.text(x, y + 0.8, f"{y}%", ha="center", fontsize=9, weight="bold", color=t["fg"])
    a2.set_xlim(2014, 2022); a2.set_ylim(0, 14)
    a2.set_ylabel("% commit có ≥ 1 annotation")
    a2.set_title("Chấp nhận annotation (Di Grazia & Pradel 2022)")
    a2.text(2018, 1.2, "9.655 dự án; chỉ 2 mốc được công bố", ha="center", fontsize=7.6, color=t["fg2"])
    ygrid(a1, t); ygrid(a2, t)


# ---------------------------------------------------------------- parse vs validate
@figure("parse-vs-validate", size=(9.0, 4.2))
def _(fig, t):
    ax = canvas(fig, (0, 128), (0, 58))
    cr, cg = t["c"][RED], t["c"][GREEN]
    ax.text(2, 54.5, "Shotgun validation: kiểm tra rải rác giữa các hành động", fontsize=9.2, weight="bold", color=cr)
    steps = [("dict thô", t["line"]), ("if 'lines' in d", cr), ("ghi hóa đơn", t["c"][BLUE]), ("for dòng: kiểm tra", cr),
             ("ghi dòng 1..6", t["c"][BLUE]), ("dòng 7 thiếu\nquantity → lỗi!", cr)]
    x = 2
    for s, c in steps:
        box(ax, x, 40, 18.5, 9.5, s, t, color=c, fill=tint(c, t, .12), fs=7.9)
        if x > 2:
            arrow(ax, x - 2.4, 44.75, x - 0.1, 44.75, t)
        x += 21
    ax.text(2, 35.5, "→ đã ghi một phần; quy tắc lặp lại ở nhiều hàm; hàm sau không biết dữ liệu đã kiểm tra chưa",
            fontsize=8.2, color=t["fg2"])
    ax.text(2, 28.5, "Parse, don't validate: nhận dạng đầy đủ ở cửa, sau đó chỉ có kiểu đã kiểm tra", fontsize=9.2,
            weight="bold", color=cg)
    box(ax, 2, 12, 18.5, 10, "bytes", t, color=t["line"], fs=8.4)
    arrow(ax, 20.8, 17, 26.8, 17, t)
    box(ax, 27, 10, 26, 14, "Invoice.model_validate_json\n(tất cả quy tắc tầng 1–3)", t, color=cg,
        fill=tint(cg, t, .16), fs=8.2, weight="bold")
    arrow(ax, 53.3, 20, 61.8, 20, t, color=cg)
    ax.text(57.5, 21.5, "Invoice", fontsize=7.8, color=cg, ha="center")
    box(ax, 62, 14, 30, 12, "logic nghiệp vụ\nnhận Invoice (bằng chứng)", t, color=t["c"][BLUE], fill=tint(t["c"][BLUE], t, .12), fs=8.2)
    arrow(ax, 92.3, 20, 98.8, 20, t)
    box(ax, 99, 14, 26, 12, "ghi DB trong\n1 transaction", t, color=t["c"][BLUE], fill=tint(t["c"][BLUE], t, .12), fs=8.2)
    arrow(ax, 40, 9.8, 40, 4.2, t, color=cr)
    ax.text(42, 4.5, "sai → 422 với TẤT CẢ lỗi, chưa có tác dụng phụ nào xảy ra", fontsize=8.2, color=cr)


# ---------------------------------------------------------------- phân cấp Chomsky
@figure("chomsky", size=(8.6, 4.2))
def _(fig, t):
    ax = canvas(fig, (0, 120), (0, 60))
    layers = [((48, 29), 92, 56, "Đệ quy liệt kê (Turing-đầy đủ)", "đầu vào là «chương trình»: eval, template, pickle", RED),
              ((44, 27), 74, 44, "Cảm ngữ cảnh / cần số học", "tổng = Σ dòng; amount = qty × price", ORANGE),
              ((40, 25), 54, 31, "Phi ngữ cảnh", "cú pháp JSON; cấu trúc hóa đơn lồng nhau", BLUE),
              ((36, 23), 32, 17, "Chính quy", "MST 10/13 số; vat_rate; ngày ISO", GREEN)]
    for (cx, cy), w, h, name, ex, c in layers:
        col = t["c"][c]
        ax.add_patch(Ellipse((cx, cy), w, h, fc=tint(col, t, .1), ec=col, lw=1.6))
    ax.text(36, 25, "Chính quy\nMST, vat_rate,\nngày ISO", ha="center", va="center", fontsize=7.6, color=t["fg"])
    ax.text(57, 26, "Phi ngữ cảnh\nJSON, cấu trúc\nlồng nhau", ha="center", va="center", fontsize=7.6, color=t["fg"])
    ax.text(74, 30, "Cảm ngữ cảnh\ntổng = Σ dòng", ha="center", va="center", fontsize=7.6, color=t["fg"])
    ax.text(66, 8.5, "Turing-đầy đủ: eval, pickle, template", ha="center", va="center", fontsize=7.6, color=t["c"][RED])
    rows = [("regex / Literal", GREEN), ("parser JSON + core schema (Rust)", BLUE),
            ("validator Python", ORANGE), ("KHÔNG chấp nhận làm đầu vào", RED)]
    ax.text(97, 33, "Bộ nhận dạng:", fontsize=8.6, weight="bold", color=t["fg"])
    for i, (s, c) in enumerate(rows):
        ax.scatter([97.5], [28.5 - i * 5], color=t["c"][c], s=30)
        ax.text(99, 28.5 - i * 5, s, fontsize=7.8, va="center", color=t["fg2"])
    ax.text(2, 57, "LangSec: xếp từng quy tắc vào lớp ngôn ngữ yếu nhất đủ dùng", fontsize=9.4, weight="bold", color=t["fg"])


# ---------------------------------------------------------------- parser differential (số liệu chạy thật)
@figure("differential", size=(8.6, 3.6))
def _(fig, t):
    ax = fig.subplots()
    cases = ["khóa trùng", "số nguyên 2⁶⁴", "1e400", "NaN", "BOM UTF-8", "surrogate lẻ", "dấu phẩy thừa"]
    libs = ["json.loads", "orjson", "msgspec", "Pydantic (jiter)"]
    # 0 = chấp nhận đúng, 1 = chấp nhận nhưng đổi nghĩa / phi chuẩn, 2 = từ chối
    M = [[1, 1, 1, 1], [0, 1, 0, 0], [1, 2, 2, 1], [1, 2, 2, 1], [1, 2, 2, 2], [1, 2, 2, 2], [2, 2, 2, 2]]
    txt = [["→ 999", "→ 999", "→ 999", "→ 999"], ["int", "float!", "int", "int"], ["inf", "lỗi", "lỗi", "inf"],
           ["nan", "lỗi", "lỗi", "nan"], ["nhận", "lỗi", "lỗi", "lỗi"], ["nhận", "lỗi", "lỗi", "lỗi"], ["lỗi", "lỗi", "lỗi", "lỗi"]]
    colors = {0: t["c"][GREEN], 1: t["c"][YELLOW], 2: t["muted"]}
    for i in range(len(cases)):
        for j in range(4):
            c = colors[M[i][j]]
            ax.add_patch(__import__("matplotlib").patches.FancyBboxPatch((j + 0.06, i + 0.08), 0.88, 0.84,
                         boxstyle="round,pad=0,rounding_size=0.08", fc=tint(c, t, .3), ec=c, lw=1))
            ax.text(j + 0.5, i + 0.5, txt[i][j], ha="center", va="center", fontsize=8.4, color=t["fg"])
    ax.set_xlim(0, 4); ax.set_ylim(len(cases), 0)
    ax.set_xticks(np.arange(4) + 0.5, libs); ax.xaxis.tick_top()
    ax.set_yticks(np.arange(len(cases)) + 0.5, cases)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    ax.set_title("Cùng byte, bốn bộ parse (Python 3.13, chạy thật) — vàng: nhận nhưng phi chuẩn/đổi nghĩa",
                 pad=24, fontsize=9.2)


# ---------------------------------------------------------------- Postel: tập chấp nhận
@figure("postel", size=(8.4, 3.6))
def _(fig, t):
    ax = canvas(fig, (0, 116), (0, 50))
    cs, cl = t["c"][BLUE], t["c"][ORANGE]
    ax.add_patch(Ellipse((38, 24), 66, 40, fc=tint(cl, t, .1), ec=cl, lw=1.6, ls="--"))
    ax.add_patch(Ellipse((30, 24), 34, 24, fc=tint(cs, t, .18), ec=cs, lw=1.8))
    ax.text(30, 30, "A_strict", ha="center", fontsize=9, weight="bold", color=cs)
    ax.text(30, 22, "82500 → 82500\n\"2026-10-13T11:45+07:00\"", ha="center", fontsize=7.8, color=t["fg"])
    ax.text(58, 38, "A_lax \\ A_strict", ha="center", fontsize=9, weight="bold", color=cl)
    ax.text(57, 27, "\"82500\" → 82500\n82500.0 → 82500", ha="center", fontsize=7.8, color=t["fg"])
    ax.text(57, 14, "\"82.500\" → lỗi hay 82,5?\n(phân cách nghìn kiểu VN)", ha="center", fontsize=7.8, color=t["c"][RED])
    ax.text(76, 40, "Đường truyền là chuỗi (path, query,\nheader, form, env) → lax là cần thiết",
            fontsize=8.2, color=t["fg"], va="top")
    ax.text(76, 27, "JSON body tài chính → strict:\nchênh lệch giữa hai tập là lỗi\ntích hợp của client, đừng che",
            fontsize=8.2, color=t["fg"], va="top")
    ax.text(76, 11, "RFC 9413: dễ dãi khi nhận làm\n«ngôn ngữ thực tế» phình ra\nso với đặc tả", fontsize=8.2,
            color=t["fg2"], va="top")
    ax.text(2, 47, "Tập đầu vào được chấp nhận: strict ⊂ lax, cùng kết quả trên phần chung", fontsize=9.4,
            weight="bold", color=t["fg"])


# ---------------------------------------------------------------- fail-fast vs tích lũy
@figure("accumulate", size=(7.8, 3.0))
def _(fig, t):
    ax = fig.subplots()
    k = np.arange(0, 11)
    ax.step(k, k + 1, where="mid", color=t["c"][RED], label="fail-fast: k + 1 lượt gửi")
    ax.step(k, np.where(k > 0, 2, 1), where="mid", color=t["c"][GREEN], label="tích lũy lỗi: ≤ 2 lượt gửi")
    ax.scatter([5], [6], color=t["c"][RED], zorder=3)
    ax.annotate("hóa đơn sai 5 chỗ\n→ 6 vòng gửi–sửa", (5, 6), (6.3, 7.6), fontsize=8.2, color=t["fg"],
                arrowprops=dict(arrowstyle="->", color=t["fg2"]))
    ax.set_xlabel("số lỗi độc lập k trong payload"); ax.set_ylabel("số lần client phải gửi")
    ax.set_title("Vì sao bộ parse nên trả mọi lỗi độc lập cùng lúc")
    ax.legend(fontsize=8.4, loc="upper left")
    ax.set_xlim(-0.3, 10.3); ax.set_ylim(0, 12)
    ygrid(ax, t)


# ---------------------------------------------------------------- 5 tầng quy tắc
@figure("layers", size=(9.0, 4.3))
def _(fig, t):
    ax = canvas(fig, (0, 128), (0, 60))
    tiers = [("0 · Vận chuyển", "body ≤ 2 MB, Content-Type", "proxy / middleware", "~0", t["muted"]),
             ("1 · Cú pháp", "JSON hợp lệ, UTF-8 hợp lệ", "parser JSON (Rust)", "~1 µs/KB", t["c"][VIOLET]),
             ("2 · Cấu trúc & trường", "đủ trường, đúng kiểu, qty > 0, regex MST", "core schema (Rust)", "chục µs", t["c"][BLUE]),
             ("3 · Ngữ nghĩa trong object", "checksum MST, amount, tổng khớp", "validator Python", "chục µs", t["c"][ORANGE]),
             ("4 · Ngữ cảnh & trạng thái", "MST thuộc tenant, số HĐ chưa dùng", "dependency + DB", "ms", t["c"][RED])]
    for i, (name, ex, where, cost, c) in enumerate(tiers):
        y = 47 - i * 10
        inset = i * 3.5
        box(ax, 2 + inset, y, 70 - 2 * inset, 8, name, t, color=c, fill=tint(c, t, .18), fs=8.6, weight="bold")
        ax.text(76, y + 5.2, ex, fontsize=8, color=t["fg"])
        ax.text(76, y + 1.6, f"{where} · {cost}", fontsize=7.8, color=t["fg2"])
    ax.text(2, 57, "Phễu quy tắc của POST /v1/invoices: rẻ trước, đắt sau; mỗi tầng chỉ nhận đầu ra của tầng trước",
            fontsize=9.2, weight="bold", color=t["fg"])
    ax.annotate("", xy=(37, 2), xytext=(37, 6.5), arrowprops=dict(arrowstyle="-|>", color=t["c"][GREEN], lw=2))
    ax.text(40, 2.5, "Invoice đã kiểm tra → logic nghiệp vụ", fontsize=8.2, color=t["c"][GREEN])


if __name__ == "__main__":
    run("01")
