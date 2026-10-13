"""Hình minh họa cho Module 07 — FastAPI: vòng đời một request."""
import numpy as np

from figkit import (AQUA, BLUE, GREEN, MAGENTA, ORANGE, RED, VIOLET, YELLOW, arrow, bench, box,
                    canvas, figure, run, tint, xgrid, ygrid)


@figure("dependant", size=(9.4, 4.4))
def _(fig, t):
    ax = canvas(fig, (0, 132), (0, 62))
    ax.text(2, 58, "Lúc khai báo route: chữ ký hàm → cây Dependant (một lần, lúc import)", fontsize=9.2,
            weight="bold", color=t["fg"])
    box(ax, 2, 40, 44, 14, "def create(\n  tenant_id: int,  item: Item,\n  x_request_id: Annotated[str|None, Header()],\n  dry_run: bool = False)", t,
        color=t["line"], fs=7.4, ha="left")
    arrow(ax, 46.3, 47, 53.7, 47, t)
    box(ax, 54, 40, 22, 14, "get_dependant()\ninspect + type hint\n+ Annotated metadata", t, color=t["c"][BLUE],
        fill=tint(t["c"][BLUE], t, .15), fs=7.8)
    cats = [("path_params: tenant_id", VIOLET), ("query_params: dry_run", AQUA), ("header_params: x-request-id", ORANGE),
            ("body: Item (model Pydantic)", BLUE), ("dependencies: [] (Module 08)", GREEN)]
    for i, (s, c) in enumerate(cats):
        y = 50 - i * 7
        col = t["c"][c]
        box(ax, 86, y, 44, 5.4, s, t, color=col, fill=tint(col, t, .15), fs=7.8, ha="left")
        arrow(ax, 76.3, 47, 85.7, y + 2.7, t, color=t["fg2"], lw=1)
    ax.text(2, 28, "Cũng dựng một lần:", fontsize=8.8, weight="bold", color=t["fg"])
    extras = [("body field", "1 model → chính model đó; nhiều tham số body → model bọc\n(Body_two_two_post), client gửi {\"item\":…, \"note\":…}"),
              ("response field", "từ response_model= hoặc kiểu trả về (-> InvoiceOut)"),
              ("schema OpenAPI", "parameters (in: path/query/header), requestBody, responses")]
    for i, (k, v) in enumerate(extras):
        y = 21 - i * 8
        box(ax, 2, y - 1.5, 22, 6, k, t, color=t["c"][MAGENTA], fill=tint(t["c"][MAGENTA], t, .14), fs=7.8)
        ax.text(27, y + 1.5, v, fontsize=7.6, color=t["fg2"], va="center")


@figure("pipeline", size=(9.4, 5.0))
def _(fig, t):
    ax = canvas(fig, (0, 132), (0, 70))
    layers = [("ServerErrorMiddleware — ngoại lệ chưa bắt → 500", t["muted"]),
              ("RequestBodyLimitMiddleware (tùy chọn) — 413", t["c"][VIOLET]),
              ("Middleware của bạn (thêm sau = ngoài cùng)", t["c"][AQUA]),
              ("ExceptionMiddleware — HTTPException → response", t["muted"]),
              ("Router — khớp path + method", t["c"][AQUA])]
    for i, (s, c) in enumerate(layers):
        hx, top, bot = i * 2.2, 66 - i * 5, 2 + i * 0.8
        box(ax, 2 + hx, bot, 62 - 2 * hx, top - bot, "", t, color=c, fill=tint(c, t, .04 + 0.03 * i), lw=1.3)
        ax.text(4 + hx, top - 3.4, s, fontsize=7.6, color=c if c != t["muted"] else t["fg2"], weight="bold")
    steps = [("1 đọc body: request.body() → request.json()\n   (json.loads; cần Content-Type JSON)", BLUE),
             ("2 solve_dependencies: path/query/header/cookie,\n   validate body bằng Pydantic, dependency con", BLUE),
             ("3 gọi handler: async def trên event loop,\n   def qua run_in_threadpool", GREEN),
             ("4 serialize_response: validate + lọc theo\n   response field → JSON", BLUE),
             ("5 dọn dependency có yield", GREEN)]
    for i, (s, c) in enumerate(steps):
        y = 33.5 - i * 6.5
        col = t["c"][c]
        box(ax, 13, y, 44, 5.6, s, t, color=col, fill=tint(col, t, .14), fs=6.9, ha="left")
    ax.text(68, 62, "Bên trong route (fastapi/routing.py)", fontsize=8.8, weight="bold", color=t["fg"])
    notes = [("lỗi ở bước 2 → RequestValidationError → 422", RED),
             ("response sai ở bước 4 → ResponseValidationError → 500", RED),
             ("HTTPException ở bước 3 → ExceptionMiddleware", ORANGE),
             ("ngoại lệ khác → ServerErrorMiddleware → 500", ORANGE)]
    for i, (s, c) in enumerate(notes):
        ax.text(68, 52 - i * 6, "• " + s, fontsize=7.8, color=t["c"][c])
    ax.text(68, 24, "Đo trong tiến trình (hóa đơn 12 dòng):", fontsize=8, weight="bold", color=t["fg"])
    ax.text(68, 19, "• khung sườn GET /health: ~54 µs\n• POST /invoices mặc định: ~135 µs\n• tự model_validate_json: ~86 µs",
            fontsize=7.8, color=t["fg2"], va="top")


@figure("response", size=(8.4, 3.2))
def _(fig, t):
    ax = fig.subplots()
    rows = bench("inside_fastapi")["variants"]
    labels = {"GET /health (dict)": "GET /health → dict",
              "POST /invoices → dict": "POST → dict (jsonable_encoder)",
              "POST /invoices → response_model nhỏ": "POST → response model nhỏ",
              "POST /invoices → trả lại cả hóa đơn": "POST → trả lại cả hóa đơn",
              "POST /invoices, tự model_validate_json": "POST, tự model_validate_json"}
    cols = [t["muted"], t["c"][ORANGE], t["c"][BLUE], t["c"][VIOLET], t["c"][GREEN]]
    y = np.arange(len(rows))
    vals = [r["us"] for r in rows]
    ax.barh(y, vals, color=cols, height=0.56)
    for i, v in enumerate(vals):
        ax.text(v + 2, i, f"{v:.0f} µs", va="center", fontsize=8.4, color=t["fg"])
    ax.set_yticks(y, [labels[r["name"]] for r in rows], fontsize=8.2); ax.invert_yaxis()
    ax.set_xlim(0, max(vals) * 1.22)
    ax.set_xlabel("µs / request, đo trong tiến trình (không mạng), hóa đơn 12 dòng")
    ax.set_title("Số đo thật: chi phí theo cách khai báo body và response")
    xgrid(ax, t)


@figure("errors", size=(9.2, 3.8))
def _(fig, t):
    ax = canvas(fig, (0, 130), (0, 52))
    cr, cg = t["c"][RED], t["c"][GREEN]
    ax.text(2, 48, "Mặc định (422)", fontsize=9, weight="bold", color=cr)
    box(ax, 2, 6, 58, 38, "", t, color=cr, fill=tint(cr, t, .06))
    left = ['{"detail": [', '  {"type": "greater_than",', '   "loc": ["body","qty"],', '   "msg": "Input should be …",',
            '   "input": 0,          ← phản chiếu dữ liệu', '   "ctx": {"gt": 0}}]}']
    for i, s in enumerate(left):
        ax.text(4, 39 - i * 5, s, fontsize=7.8, family="monospace", color=cr if "input" in s else t["fg"])
    ax.text(70, 48, "Problem Details (RFC 9457)", fontsize=9, weight="bold", color=cg)
    box(ax, 70, 6, 58, 38, "", t, color=cg, fill=tint(cg, t, .06))
    right = ['content-type: application/problem+json', '{"type": "…/problems/validation",', ' "title": "Dữ liệu không hợp lệ",',
             ' "status": 422, "instance": "/v1/invoices",', ' "errors": [{"field": "lines.0.qty",', '   "source": "body", "code": "greater_than",',
             '   "message": "Phải lớn hơn 0"}]}']
    for i, s in enumerate(right):
        ax.text(72, 40 - i * 4.7, s, fontsize=7.4, family="monospace", color=t["fg"])
    arrow(ax, 60.3, 25, 69.7, 25, t, color=cg)


@figure("middleware", size=(9.0, 3.4))
def _(fig, t):
    a1, a2 = fig.subplots(1, 2, gridspec_kw=dict(width_ratios=[1.25, 1], wspace=0.35))
    rows = bench("concurrency")["e8_middleware"]
    lab = {("none", 0): "không có", ("base", 1): "1 × Base", ("base", 2): "2 × Base", ("base", 5): "5 × Base",
           ("asgi", 1): "1 × ASGI", ("asgi", 5): "5 × ASGI"}
    names = [lab[(r["kind"], r["layers"])] for r in rows]
    vals = [r["rps"] for r in rows]
    cols = [t["muted"] if r["kind"] == "none" else t["c"][RED] if r["kind"] == "base" else t["c"][GREEN] for r in rows]
    a1.bar(range(len(rows)), vals, color=cols, width=0.62)
    for i, v in enumerate(vals):
        a1.text(i, v + 120, f"{v:,.0f}".replace(",", "."), ha="center", fontsize=7.6, color=t["fg"])
    a1.set_xticks(range(len(rows)), names, fontsize=7.8)
    a1.set_ylabel("request/giây (GET /health)"); a1.set_ylim(0, 10500)
    a1.set_title("Server thật: httptools + uvloop, 32 kết nối")
    ygrid(a1, t)
    mw = bench("inside_fastapi")["middleware"]
    for kind, c, l in (("BaseHTTPMiddleware", RED, "BaseHTTPMiddleware"), ("ASGI thuần", GREEN, "ASGI thuần")):
        rr = [r for r in mw if r["kind"] == kind]
        a2.plot([r["layers"] for r in rr], [r["us"] for r in rr], marker="o", color=t["c"][c], label=l)
    a2.set_xlabel("số lớp middleware"); a2.set_ylabel("µs / request (trong tiến trình)")
    a2.set_title("Mỗi lớp Base ~120 µs"); a2.set_xticks([0, 1, 5])
    a2.legend(fontsize=7.8); ygrid(a2, t)


@figure("streaming", size=(9.2, 3.8))
def _(fig, t):
    ax = canvas(fig, (0, 130), (0, 52))
    ax.text(2, 48, "Agent CS chờ bản nháp từ ai-gateway (LLM ~25 s)", fontsize=9.2, weight="bold", color=t["fg"])
    ax.text(2, 40, "Không stream", fontsize=8.4, color=t["c"][RED], weight="bold")
    box(ax, 22, 37, 86, 6, "màn hình trắng …", t, color=t["muted"], fill=tint(t["muted"], t, .08), fs=7.8)
    box(ax, 108.5, 37, 18, 6, "toàn bộ", t, color=t["c"][RED], fill=tint(t["c"][RED], t, .2), fs=7.8)
    ax.text(2, 28, "SSE / JSONL", fontsize=8.4, color=t["c"][GREEN], weight="bold")
    for i in range(12):
        x = 22 + i * 8.6
        box(ax, x, 25, 7.6, 6, f"#{i}", t, color=t["c"][GREEN], fill=tint(t["c"][GREEN], t, .2), fs=7)
    ax.annotate("", xy=(126, 21), xytext=(22, 21), arrowprops=dict(arrowstyle="-|>", color=t["fg2"]))
    ax.text(74, 17.5, "thời gian →  (mảnh đầu tiên sau ~1 s)", ha="center", fontsize=7.8, color=t["fg2"])
    wire = ['data: {"seq":0,"text":"Chào anh"}', "", 'data: {"seq":1,"text":", cảm ơn …"}', "",
            "event: done", 'data: {"ok": true}', "id: 12"]
    box(ax, 2, 1, 60, 13, "", t, color=t["line"], fill=t["panel"])
    for i, s in enumerate([w for w in wire if w]):
        ax.text(4, 11.5 - i * 2.1, s, fontsize=6.8, family="monospace", color=t["fg"])
    ax.text(66, 9, "FastAPI 0.143: generator → application/jsonl\nresponse_class=EventSourceResponse → text/event-stream\nchạy được với POST (giao thức MCP)",
            fontsize=7.8, color=t["fg2"], va="center")


@figure("profile", size=(8.4, 2.8))
def _(fig, t):
    ax = fig.subplots()
    prof = bench("inside_fastapi")["profile"]
    order = ["FastAPI", "Starlette", "khác (stdlib, json, typing…)", "Pydantic (Python + Rust)", "code của bạn (handler, validator)", "asyncio"]
    cols = {"FastAPI": t["c"][BLUE], "Starlette": t["c"][AQUA], "khác (stdlib, json, typing…)": t["muted"],
            "Pydantic (Python + Rust)": t["c"][VIOLET], "code của bạn (handler, validator)": t["c"][GREEN], "asyncio": t["c"][YELLOW]}
    left = 0
    for k in order:
        v = prof.get(k, 0) * 100
        ax.barh(0, v, left=left, color=cols[k], height=0.5, label=f"{k}: {v:.0f}%")
        if v > 5:
            ax.text(left + v / 2, 0, f"{v:.0f}%", ha="center", va="center", fontsize=8.4, color="white", weight="bold")
        left += v
    ax.set_xlim(0, 100); ax.set_yticks([]); ax.set_xlabel("% thời gian tự thân (cProfile, 3.000 request POST /invoices)")
    ax.set_title("Một request hóa đơn (không DB) tiêu thời gian cho ai")
    ax.legend(fontsize=7.4, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.55))
    for s in ("left",):
        ax.spines[s].set_visible(False)


@figure("case", size=(9.4, 4.0))
def _(fig, t):
    ax = canvas(fig, (0, 132), (0, 56))
    ax.text(2, 52, "POST /v1/invoices — mỗi phần do module nào phụ trách", fontsize=9.2, weight="bold", color=t["fg"])
    parts = [("RequestBodyLimit 2 MB\nRequestId · CORS", "07", AQUA), ("inv: InvoiceIn\ntầng 1–3", "03–05", BLUE),
             ("Idempotency-Key", "02, 10", ORANGE), ("current_tenant\n(xác thực, tầng 4)", "08, 11", RED),
             ("invoice_repo\ncreate_once", "08, 10", VIOLET), ("async def?\nthreadpool?", "09", MAGENTA),
             ("-> InvoiceOut\n201 + Location", "05, 07", GREEN), ("Problem Details\n422/409", "07", YELLOW)]
    for i, (s, m, c) in enumerate(parts):
        row, col = divmod(i, 4)
        x, y = 2 + col * 32.5, 28 - row * 22
        cc = t["c"][c]
        box(ax, x, y, 30, 16, s, t, color=cc, fill=tint(cc, t, .14), fs=8)
        ax.text(x + 28.5, y + 13.5, f"M{m}", ha="right", fontsize=7.4, color=cc, weight="bold")


if __name__ == "__main__":
    run("07")
