"""Hình minh họa cho Module 02 — HTTP, REST & ASGI."""
import numpy as np

from figkit import (AQUA, BLUE, GREEN, MAGENTA, ORANGE, RED, VIOLET, YELLOW, arrow, bench, box,
                    canvas, figure, run, tint, xgrid, ygrid)


# ---------------------------------------------------------------- tính chất method
@figure("methods", size=(8.6, 3.4))
def _(fig, t):
    ax = canvas(fig, (0, 118), (0, 46))
    ms = ["GET", "HEAD", "OPTIONS", "PUT", "DELETE", "POST", "PATCH"]
    props = {"GET": (1, 1, 1), "HEAD": (1, 1, 1), "OPTIONS": (1, 1, 0), "PUT": (0, 1, 0),
             "DELETE": (0, 1, 0), "POST": (0, 0, 0), "PATCH": (0, 0, 0)}
    cols = ["safe", "idempotent", "cacheable"]
    for j, c in enumerate(cols):
        ax.text(34 + j * 22, 41, c, ha="center", fontsize=9, weight="bold", color=t["fg"])
    for i, m in enumerate(ms):
        y = 34 - i * 5
        ax.text(4, y, m, fontsize=9, family="monospace", weight="bold", color=t["fg"], va="center")
        for j, v in enumerate(props[m]):
            c = t["c"][GREEN] if v else t["muted"]
            box(ax, 26 + j * 22, y - 2, 16, 4, "có" if v else "không", t, color=c, fill=tint(c, t, .2 if v else .08), fs=7.8)
    ax.text(96, 30, "POST tạo hóa đơn\nKHÔNG idempotent\n→ cần Idempotency-Key", fontsize=8.4, color=t["c"][RED], va="center")
    ax.text(96, 14, "safe ⊂ idempotent:\nmọi method safe đều\nidempotent", fontsize=8.2, color=t["fg2"], va="center")


# ---------------------------------------------------------------- idempotency
@figure("idempotency", size=(9.4, 4.4))
def _(fig, t):
    ax = canvas(fig, (0, 134), (0, 62))
    # biểu đồ tuần tự
    lanes = [("POS", 8), ("invoice-api", 34), ("DB", 58)]
    for name, x in lanes:
        box(ax, x - 7, 54, 14, 6, name, t, color=t["line"], fs=8.2, weight="bold")
        ax.plot([x, x], [6, 54], color=t["line"], lw=1, ls=":")
    def msg(x1, x2, y, s, c=None, ls="-"):
        arrow(ax, x1, y, x2, y, t, color=c or t["fg2"], ls=ls, lw=1.3)
        ax.text((x1 + x2) / 2, y + 1.2, s, ha="center", fontsize=7.6, color=c or t["fg"])
    msg(8, 34, 48, "POST, Idempotency-Key: k1")
    msg(34, 58, 44, "INSERT hóa đơn #1024 + lưu k1")
    msg(58, 34, 40, "OK")
    msg(34, 20, 36, "201 …", c=t["c"][RED], ls="--")
    ax.text(16, 33.5, "✕ mất response", fontsize=7.8, color=t["c"][RED])
    msg(8, 34, 26, "gửi lại, cùng k1")
    msg(34, 58, 22, "tìm k1 → đã có")
    msg(34, 8, 16, "201 (kết quả đã lưu, KHÔNG tạo mới)", c=t["c"][GREEN])
    ax.text(2, 8, "Không có khóa: lần gửi lại tạo hóa đơn #1025 → trùng", fontsize=8, color=t["c"][RED])
    # biểu đồ kỳ vọng
    sub = fig.add_axes([0.6, 0.18, 0.37, 0.62])
    p = np.array([0.0001, 0.0005, 0.001, 0.005, 0.01])
    N = 1.08e6
    sub.plot(p * 100, N * p, marker="o", color=t["c"][RED])
    sub.scatter([0.1], [1080], s=70, color=t["c"][RED], zorder=3)
    sub.annotate("p = 0,1% → ~1.080\nhóa đơn trùng/ngày", (0.1, 1080), (0.35, 4500), fontsize=8, color=t["fg"],
                 arrowprops=dict(arrowstyle="->", color=t["fg2"]))
    sub.set_xlabel("p: % lần tạo mất response (%)"); sub.set_ylabel("hóa đơn trùng / ngày")
    sub.set_title("Nếu thiếu idempotency (N = 1,08 triệu POST/ngày)", fontsize=8.8)
    ygrid(sub, t)


# ---------------------------------------------------------------- ràng buộc REST
@figure("rest", size=(8.8, 3.4))
def _(fig, t):
    ax = canvas(fig, (0, 124), (0, 46))
    cons = [("Client–server", "tách UI và lưu trữ", True), ("Stateless", "mỗi request đủ thông tin\n→ worker nào cũng xử lý được", True),
            ("Cache", "response tự đánh dấu", True), ("Uniform interface", "URI, representation,\nthông điệp tự mô tả", True),
            ("HATEOAS", "hypermedia dẫn đường", False), ("Layered system", "LB, proxy trong suốt", True)]
    for i, (n, d, used) in enumerate(cons):
        x = 2 + (i % 3) * 41
        y = 26 if i < 3 else 6
        c = t["c"][GREEN] if used else t["muted"]
        box(ax, x, y, 39, 15, "", t, color=c, fill=tint(c, t, .12 if used else .05), ls="-" if used else "--")
        ax.text(x + 2, y + 11, n, fontsize=8.8, weight="bold", color=t["fg"])
        ax.text(x + 2, y + 6.5, d, fontsize=7.8, color=t["fg2"], va="top")
        ax.text(x + 37, y + 11, "invoice-api: có" if used else "bỏ qua (client POS lập trình sẵn)",
                fontsize=7.2, ha="right", color=c)
    ax.text(2, 43.5, "Ràng buộc REST (Fielding 2000) và lựa chọn của invoice-api", fontsize=9.4, weight="bold", color=t["fg"])


# ---------------------------------------------------------------- phân trang (số đo thật)
@figure("pagination", size=(8.2, 3.2))
def _(fig, t):
    ax = fig.subplots()
    rows = bench("pagination")
    pg = [r["page"] for r in rows]
    ax.plot(pg, [r["offset_ms"] for r in rows], marker="o", color=t["c"][RED], label="OFFSET (page − 1) × 50")
    ax.plot(pg, [r["cursor_ms"] for r in rows], marker="s", color=t["c"][GREEN], label="cursor (issued_at, id) < (…)")
    ax.set_xscale("log"); ax.set_yscale("log")
    last = rows[-1]
    ax.annotate(f"trang {last['page']:,}: {last['offset_ms']:.0f} ms\nso với {last['cursor_ms']:.2f} ms".replace(",", "."),
                (last["page"], last["offset_ms"]), (700, 18), fontsize=8.2, color=t["fg"],
                arrowprops=dict(arrowstyle="->", color=t["fg2"]))
    ax.set_xlabel("số thứ tự trang (50 hóa đơn/trang)"); ax.set_ylabel("ms / truy vấn")
    ax.set_title("Số đo thật: SQLite, 1 triệu hóa đơn, có index (tenant_id, issued_at, id)")
    ax.legend(fontsize=8.2, loc="upper left")
    ax.grid(color=t["grid"], lw=0.6); ax.set_axisbelow(True)


# ---------------------------------------------------------------- ASGI
@figure("asgi", size=(9.2, 4.0))
def _(fig, t):
    ax = canvas(fig, (0, 130), (0, 56))
    cs, cm, ca = t["c"][VIOLET], t["c"][AQUA], t["c"][BLUE]
    box(ax, 2, 6, 24, 44, "Server ASGI\n(Uvicorn)\n\nsocket, HTTP parser,\nevent loop", t, color=cs, fill=tint(cs, t, .12), fs=8.2)
    box(ax, 34, 6, 30, 44, "", t, color=cm, fill=tint(cm, t, .08))
    ax.text(49, 46, "Middleware (cũng là app ASGI)", ha="center", fontsize=8.4, weight="bold", color=cm)
    box(ax, 38, 10, 22, 30, "app(scope,\nreceive,\nsend_wrapper)", t, color=ca, fill=tint(ca, t, .14), fs=8)
    box(ax, 72, 6, 56, 44, "", t, color=ca, fill=tint(ca, t, .06))
    ax.text(100, 46, "Ứng dụng (Starlette / FastAPI)", ha="center", fontsize=8.4, weight="bold", color=ca)
    evs = [("scope: {type: http, method: POST, path: /v1/invoices, headers…}", 38),
           ("await receive() → {type: http.request, body: b'…', more_body: False}", 31),
           ("await send({type: http.response.start, status: 201, headers})", 22),
           ("await send({type: http.response.body, body: b'{…}'})", 15)]
    for s, y in evs:
        ax.text(74, y, s, fontsize=7.4, family="monospace", color=t["fg"])
    arrow(ax, 26.3, 38, 37.8, 38, t); arrow(ax, 60.3, 38, 71.8, 38, t)
    arrow(ax, 71.8, 22, 60.3, 22, t, color=t["c"][GREEN]); arrow(ax, 37.8, 22, 26.3, 22, t, color=t["c"][GREEN])
    ax.text(2, 53, "ASGI: mọi lớp đều là coroutine app(scope, receive, send)", fontsize=9.4, weight="bold", color=t["fg"])


# ---------------------------------------------------------------- event loop
@figure("event-loop", size=(8.8, 4.2))
def _(fig, t):
    ax = canvas(fig, (0, 122), (0, 58))
    cx, cy, R = 40, 28, 19
    th = np.linspace(0, 2 * np.pi, 200)
    ax.plot(cx + R * np.cos(th), cy + R * np.sin(th), color=t["line"], lw=1.6)
    steps = [(90, "1. tính timeout\n(timer gần nhất)"), (0, "2. selector.select()\nngủ trong kernel (epoll)"),
             (-90, "3. socket sẵn sàng\n→ hàng đợi ready"), (180, "4. chạy LẦN LƯỢT từng\ncallback/coroutine\nđến await kế tiếp")]
    for ang, s in steps:
        a = np.deg2rad(ang)
        x, y = cx + R * np.cos(a), cy + R * np.sin(a)
        box(ax, x - 13, y - 5, 26, 10, s, t, color=t["c"][BLUE], fill=tint(t["c"][BLUE], t, .15), fs=7.6)
    for a0 in (60, -30, -120, 150):
        a = np.deg2rad(a0)
        ax.annotate("", xy=(cx + R * np.cos(a - 0.12), cy + R * np.sin(a - 0.12)),
                    xytext=(cx + R * np.cos(a + 0.12), cy + R * np.sin(a + 0.12)),
                    arrowprops=dict(arrowstyle="-|>", color=t["fg2"]))
    # timeline bên phải
    ax.text(72, 52, "Một vòng: các coroutine chia nhau MỘT luồng", fontsize=8.8, weight="bold", color=t["fg"])
    seq = [("A", 2, BLUE), ("B", 1.5, AQUA), ("C", 2.5, VIOLET), ("A", 1, BLUE), ("D chặn 50 ms!", 13, RED), ("B", 1.5, AQUA)]
    x = 72
    for s, w, c in seq:
        col = t["c"][c]
        box(ax, x, 40, w * 1.75, 7, s if w > 1.2 else "", t, color=col, fill=tint(col, t, .3), fs=7.4, radius=0.5)
        x += w * 1.75 + 0.3
    ax.text(72, 35, "thời gian →", fontsize=7.8, color=t["fg2"])
    ax.text(72, 26, "Khi D chạy time.sleep(0.05) hoặc gọi\nthư viện đồng bộ, mọi kết nối khác\nđứng chờ — không ai ngắt được D.",
            fontsize=8.2, color=t["fg"], va="top")
    ax.text(72, 12, "Module 09 đo: async-chặn giới hạn cả\ntiến trình ở ~20 req/s.", fontsize=8.2, color=t["c"][RED], va="top")


# ---------------------------------------------------------------- bộ nhớ luồng vs coroutine (số đo thật)
@figure("mem", size=(8.4, 3.2))
def _(fig, t):
    a1, a2 = fig.subplots(1, 2, gridspec_kw=dict(wspace=0.35))
    rows = bench("threads_coroutines")
    for kind, c, lab in (("thread", ORANGE, "luồng hệ điều hành"), ("coroutine", BLUE, "task asyncio")):
        rr = [r for r in rows if r["kind"] == kind]
        a1.plot([r["n"] for r in rr], [r["rss_mb"] for r in rr], marker="o", color=t["c"][c], label=lab)
        a2.plot([r["n"] for r in rr], [r["create_s"] * 1000 for r in rr], marker="o", color=t["c"][c], label=lab)
    for a, yl, ti in ((a1, "RSS tăng thêm (MB)", "Bộ nhớ"), (a2, "thời gian tạo (ms)", "Thời gian tạo")):
        a.set_xscale("log"); a.set_yscale("log"); a.set_xlabel("số lượng đang chờ"); a.set_ylabel(yl)
        a.set_title(ti); a.grid(color=t["grid"], lw=0.6); a.set_axisbelow(True)
    th = [r for r in rows if r["kind"] == "thread"][-1]
    co = [r for r in rows if r["kind"] == "coroutine"][-1]
    a1.text(0.03, 0.85, f"~{th['kb_each']:.0f} KB/luồng\n~{co['kb_each']:.1f} KB/task", transform=a1.transAxes,
            fontsize=8, color=t["fg"])
    a2.legend(fontsize=7.8, loc="lower right")


# ---------------------------------------------------------------- GIL (số đo thật)
@figure("gil", size=(7.6, 3.0))
def _(fig, t):
    ax = fig.subplots()
    rows = bench("gil")
    ks = [1, 2, 4]
    x = np.arange(3)
    th = [next(r["seconds"] for r in rows if r["kind"] == "luồng" and r["workers"] == k) for k in ks]
    pr = [next(r["seconds"] for r in rows if r["kind"] == "tiến trình" and r["workers"] == k) for k in ks]
    ax.bar(x - 0.18, th, 0.34, color=t["c"][ORANGE], label="luồng (chung một GIL)")
    ax.bar(x + 0.18, pr, 0.34, color=t["c"][BLUE], label="tiến trình (mỗi cái một GIL)")
    for xi, v in zip(x - 0.18, th):
        ax.text(xi, v + 0.01, f"{v:.2f}s", ha="center", fontsize=8.4, color=t["fg"])
    for xi, v in zip(x + 0.18, pr):
        ax.text(xi, v + 0.01, f"{v:.2f}s", ha="center", fontsize=8.4, color=t["fg"])
    ax.set_xticks(x, [f"{k} worker" for k in ks]); ax.set_ylabel("giây cho CÙNG tổng khối lượng CPU")
    ax.set_title("Số đo thật: CPU thuần Python chia cho luồng và tiến trình (4 vCPU)")
    ax.legend(fontsize=8.2); ax.set_ylim(0, max(th + pr) * 1.25)
    ygrid(ax, t)


# ---------------------------------------------------------------- uvicorn variants (số đo thật)
@figure("uvicorn-variants", size=(8.4, 3.2))
def _(fig, t):
    ax = fig.subplots()
    rows = bench("concurrency")["e7_uvicorn_variants"]
    combos = [("h11", "asyncio"), ("httptools", "asyncio"), ("h11", "uvloop"), ("httptools", "uvloop")]
    x = np.arange(4)
    for k, (ep, c, lab) in enumerate((("/health", AQUA, "GET /health"), ("/invoices", BLUE, "POST /invoices (12 dòng)"))):
        v = [next(r["rps"] for r in rows if r["http"] == h and r["loop"] == l and r["endpoint"] == ep) for h, l in combos]
        ax.bar(x + (k - 0.5) * 0.36, v, 0.34, color=t["c"][c], label=lab)
        for xi, vi in zip(x + (k - 0.5) * 0.36, v):
            ax.text(xi, vi + 80, f"{vi:,.0f}".replace(",", "."), ha="center", fontsize=7.8, color=t["fg"])
    ax.set_xticks(x, ["h11 + asyncio\n(pip install uvicorn)", "httptools\n+ asyncio", "h11\n+ uvloop",
                      "httptools + uvloop\n(uvicorn[standard])"], fontsize=8)
    ax.set_ylabel("request/giây (1 worker, 32 kết nối)")
    ax.set_title("Số đo thật: cùng code, khác gói cài đặt")
    ax.legend(fontsize=8.2, loc="upper left"); ax.set_ylim(0, 9800)
    ygrid(ax, t)


# ---------------------------------------------------------------- hành trình request
@figure("journey", size=(9.6, 4.6))
def _(fig, t):
    ax = canvas(fig, (0, 136), (0, 64))
    steps = [("1 kernel\nTCP, epoll", VIOLET), ("2 event loop\ndata_received", VIOLET), ("3 parser HTTP\n→ scope", VIOLET),
             ("4 middleware\nCORS, telemetry", AQUA), ("5 router\nkhớp route", AQUA),
             ("6 FastAPI: body\n+ dependency\n+ Pydantic", BLUE), ("7 handler\ncủa bạn", GREEN),
             ("8 response_model\nserialize", BLUE), ("9 teardown\ncommit, ghi socket", VIOLET)]
    for i, (s, c) in enumerate(steps):
        row, col = divmod(i, 5)
        x = 2 + col * 26.6 if row == 0 else 2 + (4 - (i - 5)) * 26.6
        y = 40 if row == 0 else 12
        cc = t["c"][c]
        box(ax, x, y, 24, 13, s, t, color=cc, fill=tint(cc, t, .15), fs=7.8)
        if row == 0 and col < 4:
            arrow(ax, x + 24.2, y + 6.5, x + 26.4, y + 6.5, t)
        if row == 1 and i < 8:
            arrow(ax, x - 0.2, y + 6.5, x - 2.4, y + 6.5, t)
    arrow(ax, 2 + 4 * 26.6 + 12, 39.8, 2 + 4 * 26.6 + 12, 25.3, t)
    ax.text(2 + 4 * 26.6 + 12, 8.5, "lỗi Pydantic → 422 ngay,\nhandler không được gọi", fontsize=7.6,
            color=t["c"][RED], ha="center", va="top")
    ax.text(2, 60, "Hành trình của POST /v1/invoices qua các lớp (Module 07–09 phóng to bước 4–8)", fontsize=9.2,
            weight="bold", color=t["fg"])
    for lab, c, x in (("Uvicorn", VIOLET, 2), ("Starlette", AQUA, 22), ("FastAPI + Pydantic", BLUE, 44), ("code của bạn", GREEN, 74)):
        ax.scatter([x], [3.5], color=t["c"][c], s=30)
        ax.text(x + 1.5, 3.5, lab, fontsize=7.8, va="center", color=t["fg2"])


if __name__ == "__main__":
    run("02")
