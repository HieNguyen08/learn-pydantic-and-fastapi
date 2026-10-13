"""Hình minh họa cho Module 00 — Tổng quan & bài toán."""
import numpy as np

from figkit import (AQUA, BLUE, GREEN, MAGENTA, ORANGE, RED, VIOLET, YELLOW, arrow, box,
                    canvas, figure, note, run, tint, xgrid, ygrid)


# ---------------------------------------------------------------- ranh giới tin cậy
@figure("trust-boundaries", size=(9.2, 4.4))
def _(fig, t):
    ax = canvas(fig, (0, 130), (0, 62))
    cb, cg, co = t["c"][BLUE], t["c"][GREEN], t["c"][ORANGE]
    # vùng tin cậy
    box(ax, 38, 4, 58, 52, "", t, color=cg, fill=tint(cg, t, .07), ls="--", radius=2)
    ax.text(40, 52.5, "Vùng tin cậy: chỉ có object đã parse", fontsize=8.8, color=cg, weight="bold")
    srcs = [(44, "Máy POS / ERP\n(3.000 tenant)"), (31, "Webhook Zendesk\n(email khách)"),
            (18, "Output của LLM\n(JSON «gần đúng»)"), (5, "File cấu hình,\nhàng đợi, cache")]
    for y, s in srcs:
        box(ax, 2, y, 25, 9, s, t, color=t["line"], fs=8.4)
        # cổng parse
        box(ax, 33, y + 1.5, 9, 6, "parse", t, color=co, fill=tint(co, t, .2), fs=8.2, weight="bold")
        arrow(ax, 27.2, y + 4.5, 32.8, y + 4.5, t)
        ax.text(29.8, y + 6.4, "bytes", fontsize=7, color=t["muted"], ha="center")
    # bên trong
    box(ax, 50, 36, 30, 12, "Logic nghiệp vụ\n(chỉ nhận kiểu đã kiểm tra)", t, color=cb, fill=tint(cb, t, .15), fs=8.8)
    box(ax, 50, 12, 30, 12, "Lưu trữ / gọi ra ngoài\n(serialize có kiểm soát)", t, color=cb, fill=tint(cb, t, .15), fs=8.8)
    for y, _ in srcs:
        arrow(ax, 42.2, y + 4.5, 49.8, 42 if y > 25 else 18, t, color=t["muted"], lw=1.1)
    arrow(ax, 65, 35.8, 65, 24.2, t)
    # bên phải: từ chối
    box(ax, 100, 30, 28, 16, "Dữ liệu sai\n→ 422 + lỗi có cấu trúc\n→ từ chối, KHÔNG sập", t,
        color=t["c"][RED], fill=tint(t["c"][RED], t, .12), fs=8.4)
    arrow(ax, 42.2, 48.5, 99.5, 42, t, color=t["c"][RED], ls=":", lw=1.2, rad=-0.18)
    ax.text(84, 50, "từ chối tại cổng", fontsize=7.8, color=t["c"][RED], ha="center")
    box(ax, 100, 8, 28, 14, "Postgres, Zendesk API,\nSSE tới agent", t, color=t["line"], fs=8.4)
    arrow(ax, 80.2, 18, 99.8, 15, t)
    ax.text(2, 58.5, "Ranh giới tin cậy của Mekong Cloud: mọi nguồn bên ngoài đi qua một cổng parse duy nhất",
            fontsize=9.6, weight="bold", color=t["fg"])


# ---------------------------------------------------------------- dòng thời gian
@figure("timeline", size=(9.4, 3.6))
def _(fig, t):
    ax = canvas(fig, (2013.3, 2027.2), (-5.2, 5.6))
    ax.set_aspect("auto")
    ax.plot([2013.6, 2026.95], [0, 0], color=t["line"], lw=2)
    for y in range(2014, 2027):
        ax.plot([y, y], [-0.18, 0.18], color=t["line"], lw=1.2)
        ax.text(y, -0.75, str(y), ha="center", fontsize=7.6, color=t["muted"])
    ev = [
        (2014.9, 1, "PEP 484\ntype hints", VIOLET), (2016.9, 2.6, "PEP 526\nannotation biến", VIOLET),
        (2017.4, -2.1, "Pydantic\nra đời", BLUE), (2018.4, 1.0, "Starlette", AQUA),
        (2018.95, -3.7, "FastAPI\nra đời", ORANGE), (2019.8, 3.2, "PEP 593\nAnnotated", VIOLET),
        (2023.5, -2.1, "Pydantic v2\nlõi Rust", BLUE), (2022.0, 1.0, "PEP 681\ndataclass_transform", VIOLET),
        (2025.8, 1.0, "Python 3.14\nfree-threaded,\nPEP 649", VIOLET), (2026.22, -3.7, "Starlette 1.0", AQUA),
        (2026.78, -2.0, "Pydantic 2.14\nFastAPI 0.143", BLUE),
    ]
    shift = {"Pydantic 2.14\nFastAPI 0.143": -0.25, "Starlette 1.0": -0.35}
    for x, y, s, c in ev:
        col = t["c"][c]
        ax.plot([x, x], [0, y * 0.72], color=col, lw=1.1)
        ax.scatter([x], [0], color=col, s=26, zorder=3)
        ax.text(x + shift.get(s, 0), y, s, ha="center", va="center", fontsize=7.8, color=t["fg"],
                bbox=dict(boxstyle="round,pad=0.3", fc=tint(col, t, .16), ec=col, lw=0.9))
    for (lab, c), xx in zip([("Python typing", VIOLET), ("Pydantic", BLUE), ("Starlette", AQUA), ("FastAPI", ORANGE)],
                            (2013.6, 2016.0, 2018.0, 2020.0)):
        ax.scatter([xx], [5.1], color=t["c"][c], s=30)
        ax.text(xx + 0.18, 5.1, lab, va="center", fontsize=8, color=t["fg2"])


# ---------------------------------------------------------------- hệ sinh thái
@figure("ecosystem", size=(8.8, 3.1))
def _(fig, t):
    a1, a2 = fig.subplots(1, 2, gridspec_kw=dict(width_ratios=[1.25, 1], wspace=0.45))
    names = ["FastAPI", "Django", "Flask"]
    now = [38, 35, 34]
    prev = [29, 33, None]
    y = np.arange(3)
    a1.barh(y, now, color=[t["c"][ORANGE], t["c"][GREEN], t["c"][BLUE]], height=0.55)
    for i, (n, p) in enumerate(zip(now, prev)):
        a1.text(n + 0.6, i, f"{n}%", va="center", fontsize=9, weight="bold", color=t["fg"])
        if p:
            a1.plot([p, p], [i - 0.3, i + 0.3], color=t["fg"], lw=1.6, ls=":")
            a1.text(p - 0.5, i - 0.42, f"năm trước {p}%", fontsize=7.2, color=t["fg2"], ha="right")
    a1.set_yticks(y, names); a1.invert_yaxis(); a1.set_xlim(0, 46)
    a1.set_xlabel("% người làm web Python dùng framework")
    a1.set_title("Khảo sát Python Developers Survey (dữ liệu 2024)")
    xgrid(a1, t)
    src = ["blog Pydantic\n(02/2026)", "pepy.tech\n(30 ngày, 10/2026)"]
    vals = [550, 1055]
    a2.bar(src, vals, color=[t["c"][BLUE], tint(t["c"][BLUE], t, .55)], width=0.55)
    for i, v in enumerate(vals):
        a2.text(i, v + 25, f"{v} tr", ha="center", fontsize=9, weight="bold", color=t["fg"])
    a2.set_ylim(0, 1250); a2.set_ylabel("lượt tải pydantic / tháng (triệu)")
    a2.set_title("Hai nguồn, hai cách đếm")
    ygrid(a2, t)


# ---------------------------------------------------------------- Fermi
@figure("fermi", size=(8.4, 3.0))
def _(fig, t):
    ax = fig.subplots()
    steps = [("TB cả ngày\n1,8M/86.400 s", 1.8e6 / 86400), ("TB giờ bán\n×0,85, 12 giờ", 35),
             ("Cao điểm\ntrưa/tối ×4", 140), ("Cuối tháng\n×3", 420), ("Thiết kế\n(+ biên)", 500)]
    xs = np.arange(len(steps))
    cols = [t["muted"], t["c"][BLUE], t["c"][AQUA], t["c"][ORANGE], t["c"][RED]]
    ax.bar(xs, [v for _, v in steps], color=cols, width=0.6)
    for i, (_, v) in enumerate(steps):
        ax.text(i, v + 12, f"{v:.0f} req/s" if v >= 30 else f"{v:.1f} req/s", ha="center", fontsize=9, weight="bold", color=t["fg"])
    ax.set_xticks(xs, [s for s, _ in steps], fontsize=8.4)
    ax.set_ylim(0, 580); ax.set_ylabel("request / giây")
    ax.set_title("invoice-api: chuỗi nhân Fermi từ request/ngày đến tải thiết kế (giả định)")
    ygrid(ax, t)


# ---------------------------------------------------------------- hồ sơ tải theo giờ
@figure("load-profile", size=(8.6, 3.2))
def _(fig, t):
    ax = fig.subplots()
    m = np.arange(0, 24 * 60, 5) / 60.0            # mốc 5 phút
    night = np.where((m < 6.5) | (m > 22), 1.0, 0.0)
    biz = np.where((m >= 7) & (m <= 21), 1.0, 0.0)
    peaks = np.exp(-0.5 * ((m - 12.0) / 0.45) ** 2) + 0.92 * np.exp(-0.5 * ((m - 19.0) / 0.5) ** 2)
    # chọn mức nền b để tổng ngày = 1,8 triệu request và đỉnh trưa = 140 req/s
    def total(b):
        r = 2 * night + b * biz + (140 - b) * peaks
        return (r * 300).sum(), r
    lo, hi = 1.0, 139.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if total(mid)[0] < 1.8e6 else (lo, mid)
    _, r = total(lo)
    ax.fill_between(m, r, color=tint(t["c"][BLUE], t, .35), lw=0)
    ax.plot(m, r, color=t["c"][BLUE], lw=1.6, label="ngày thường (tổng 1,8M request)")
    ax.plot(m, 3 * r, color=t["c"][ORANGE], lw=1.6, ls="--", label="ngày cuối tháng (×3)")
    ax.axhline(500, color=t["c"][RED], lw=1.3, ls=":")
    ax.text(23.6, 512, "tải thiết kế 500 req/s", fontsize=8.2, color=t["c"][RED], ha="right")
    ax.annotate("đỉnh trưa ≈ 140 req/s", (12, 140), (14.2, 230), fontsize=8.2, color=t["fg"],
                arrowprops=dict(arrowstyle="->", color=t["fg2"]))
    ax.annotate("cuối tháng ≈ 420 req/s", (12, 420), (14.2, 440), fontsize=8.2, color=t["fg"],
                arrowprops=dict(arrowstyle="->", color=t["fg2"]))
    ax.set_xticks(range(0, 25, 2)); ax.set_xlim(0, 24); ax.set_ylim(0, 600)
    ax.set_xlabel("giờ trong ngày (UTC+7), độ phân giải 5 phút"); ax.set_ylabel("req/s")
    ax.set_title(f"Hồ sơ tải giả định của invoice-api (mức nền giờ bán ≈ {lo:.0f} req/s)")
    ax.legend(loc="upper left", fontsize=8.2)
    ygrid(ax, t)


# ---------------------------------------------------------------- hai workload
@figure("two-workloads", size=(7.6, 4.0))
def _(fig, t):
    ax = fig.subplots()
    lam = np.logspace(-2, 4, 100)
    for L in (0.1, 1, 10, 100, 1000):
        ax.plot(lam, L / lam, color=t["muted"], lw=0.9, ls=":")
        yl = 2.5e-3 if L / 2.5e-3 <= 8e3 else 300
        ax.text(L / yl, yl, f"L = {L:g}", fontsize=7.4, color=t["fg2"], ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.15", fc=t["bg"], ec="none"))
    pts = [("invoice-api\n500 req/s × 0,05 s\n→ ~25 request đang xử lý", 500, 0.05, BLUE),
           ("ai-gateway (pipeline)\n0,4 lượt/s × 15 s\n→ ~6 lượt đang chạy", 0.4, 15, ORANGE),
           ("ai-gateway (SSE)\n60 kết nối mở hàng giờ", 0.02, 3000, MAGENTA)]
    for s, x, y, c in pts:
        ax.scatter([x], [y], s=90, color=t["c"][c], zorder=3, edgecolor=t["bg"], linewidth=1.2)
        ax.text(x * 1.7, y * 0.8, s, fontsize=8, color=t["fg"], va="top")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlim(1e-2, 1e4); ax.set_ylim(1e-3, 1e4)
    ax.set_xlabel("tốc độ đến λ (request/giây)"); ax.set_ylabel("thời gian mỗi request W (giây)")
    ax.set_title("Hai workload trái ngược; đường chấm: số request đồng thời L = λ·W (Little)")
    ax.grid(color=t["grid"], lw=0.6)
    ax.set_axisbelow(True)


# ---------------------------------------------------------------- bản đồ khóa học
@figure("course-map", size=(9.4, 4.0))
def _(fig, t):
    ax = canvas(fig, (0, 132), (0, 56))
    parts = [("I · Nền tảng", ["00 Tổng quan", "01 Kiểu & validation", "02 HTTP, REST, ASGI"], VIOLET),
             ("II · Pydantic", ["03 Kiến trúc v2", "04 Validator & union", "05 Serialization", "06 Hiệu năng"], BLUE),
             ("III · FastAPI", ["07 Vòng đời request", "08 Dependency injection", "09 Async & đồng thời",
                                "10 Database", "11 Bảo mật"], ORANGE),
             ("IV · Vận hành", ["12 Testing", "13 Production", "14 Capstone"], GREEN),
             ("V · Chuyên đề", ["15 Pydantic cho LLM"], MAGENTA)]
    x = 1.5
    widths = [24, 25, 27, 25, 24]
    for (title, mods, c), w in zip(parts, widths):
        col = t["c"][c]
        box(ax, x, 3, w, 46, "", t, color=col, fill=tint(col, t, .07), radius=1.6)
        ax.text(x + w / 2, 51.5, title, ha="center", fontsize=9.4, weight="bold", color=col)
        for j, m in enumerate(mods):
            box(ax, x + 1.2, 41 - j * 8.2, w - 2.4, 6.4, m, t, color=col, fill=tint(col, t, .18), fs=8.1)
        x += w + 1.3
    ax.text(2, 0.3, "Lab 01–06 tái tạo số liệu của các module · Slide seminar tóm lược 00 → 01 → 03 → 06 → 07 → 09 → 14",
            fontsize=8.2, color=t["fg2"])


if __name__ == "__main__":
    run("00")
