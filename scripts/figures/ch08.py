"""Hình minh họa cho Module 08 — Dependency injection."""
import numpy as np

from figkit import (AQUA, BLUE, GREEN, MAGENTA, ORANGE, RED, VIOLET, YELLOW, arrow, bench, box,
                    canvas, figure, run, tint, xgrid, ygrid)


@figure("ioc", size=(9.2, 3.8))
def _(fig, t):
    ax = canvas(fig, (0, 130), (0, 52))
    cr, cg = t["c"][RED], t["c"][GREEN]
    ax.text(2, 48, "Tự lấy / service locator", fontsize=9, weight="bold", color=cr)
    box(ax, 2, 18, 30, 24, "handler\nSettings()\nconnect(...)\ndecode_jwt(...)\n… close()?", t, color=cr, fill=tint(cr, t, .1), fs=7.8)
    for i, s in enumerate(["env", "Postgres", "JWT secret"]):
        box(ax, 40, 34 - i * 9, 18, 6, s, t, color=t["line"], fs=7.8)
        arrow(ax, 32.3, 30, 39.7, 37 - i * 9, t, color=cr, lw=1)
    ax.text(2, 12, "phụ thuộc ẩn trong thân hàm,\nkhó test, dễ quên dọn dẹp", fontsize=7.8, color=t["fg2"], va="top")
    ax.text(70, 48, "Dependency injection (FastAPI)", fontsize=9, weight="bold", color=cg)
    box(ax, 70, 30, 24, 12, "FastAPI\ngiải đồ thị", t, color=t["c"][BLUE], fill=tint(t["c"][BLUE], t, .15), fs=8)
    for i, s in enumerate(["settings", "db_session", "current_tenant"]):
        box(ax, 70 + i * 20 - 4, 14, 18, 6, s, t, color=cg, fill=tint(cg, t, .12), fs=7.4)
        arrow(ax, 75 + i * 20, 20.3, 80, 29.7, t, color=cg, lw=1)
    box(ax, 104, 30, 24, 12, "handler(\n tenant, db, …)", t, color=cg, fill=tint(cg, t, .12), fs=7.8)
    arrow(ax, 94.3, 36, 103.7, 36, t, color=cg)
    ax.text(70, 9, "phụ thuộc hiện trên chữ ký · vòng đời do framework quản lý\n· thay thế bằng dependency_overrides khi test",
            fontsize=7.8, color=t["fg2"], va="top")


@figure("dag", size=(9.0, 4.0))
def _(fig, t):
    ax = canvas(fig, (0, 126), (0, 56))
    pos = {"settings": (14, 10), "db": (44, 26), "tenant": (74, 14), "repo": (74, 40), "handler": (108, 28)}
    order = {"settings": 1, "db": 2, "tenant": 3, "repo": 4, "handler": 5}
    cols = {"settings": VIOLET, "db": BLUE, "tenant": ORANGE, "repo": GREEN, "handler": MAGENTA}
    edges = [("settings", "db"), ("settings", "tenant"), ("db", "tenant"), ("db", "repo"), ("tenant", "repo"),
             ("repo", "handler"), ("settings", "handler")]
    for a, b in edges:
        (x1, y1), (x2, y2) = pos[a], pos[b]
        if x1 == x2:   # cùng cột: nối từ cạnh trên xuống cạnh dưới
            arrow(ax, x1, y1 + 7.2, x2, y2 - 0.2, t, color=t["fg2"], lw=1.1)
        else:
            arrow(ax, x1 + 9, y1 + 3.5, x2 - 9, y2 + 3.5, t, color=t["fg2"], lw=1.1)
    for k, (x, y) in pos.items():
        c = t["c"][cols[k]]
        box(ax, x - 9, y, 18, 7, k, t, color=c, fill=tint(c, t, .18), fs=8.4, weight="bold")
        ax.text(x + 9.5, y + 8, str(order[k]), fontsize=8, color="white", ha="center", va="center",
                bbox=dict(boxstyle="circle,pad=0.25", fc=c, ec="none"))
    ax.text(2, 52, "Đồ thị dependency của /ok — số trong vòng tròn: thứ tự chạy (topo)", fontsize=9.2, weight="bold", color=t["fg"])
    ax.text(2, 47, "settings được cần bởi 3 nút nhưng chạy 1 lần (cache trong request);\n"
                   "tenant và repo nhận CÙNG session db → cùng transaction", fontsize=7.8, color=t["fg2"], va="top")
    ax.text(84, 4, "teardown (yield): db commit → db đóng, sau handler", fontsize=7.8, color=t["fg2"])


@figure("yield", size=(9.4, 3.6))
def _(fig, t):
    ax = canvas(fig, (0, 132), (0, 48))
    seq = [("req: setup", VIOLET), ("fn: setup", BLUE), ("handler", MAGENTA), ("fn: teardown", BLUE),
           ("gửi response / stream", GREEN), ("req: teardown", VIOLET)]
    x = 2
    for i, (s, c) in enumerate(seq):
        w = 30 if "stream" in s else 19
        col = t["c"][c]
        box(ax, x, 22, w, 9, s, t, color=col, fill=tint(col, t, .18), fs=8)
        if i < len(seq) - 1:
            arrow(ax, x + w + 0.2, 26.5, x + w + 1.8, 26.5, t)
        x += w + 2
    ax.text(2, 42, "Thứ tự đo được: Depends(dep_req) [mặc định scope='request'] và Depends(dep_fn, scope='function')",
            fontsize=8.8, weight="bold", color=t["fg"])
    ax.text(2, 14, "scope='function': dọn TRƯỚC khi gửi response → commit xong mới trả 201 (session ghi của invoice-api)",
            fontsize=7.8, color=t["c"][BLUE])
    ax.text(2, 8, "scope='request': dọn SAU khi gửi xong → cần cho SSE/JSONL đọc DB trong generator (ai-gateway)",
            fontsize=7.8, color=t["c"][VIOLET])


@figure("patterns", size=(9.0, 3.4))
def _(fig, t):
    ax = canvas(fig, (0, 128), (0, 46))
    items = [("Alias Annotated", "CurrentTenant = Annotated[Tenant,\n  Depends(current_tenant)]", "khai báo một lần,\nmọi handler dùng lại", BLUE),
             ("Class có tham số", "RequireScope('invoice:write')\n→ __call__(principal)", "mỗi instance là một\ndependency (khóa cache riêng)", ORANGE),
             ("Cấp router / app", "APIRouter(dependencies=[…])\nFastAPI(dependencies=[…])", "chạy cho mọi route,\nkhông truyền giá trị", GREEN),
             ("Dependency trả model", "def page(cursor: str|None = None,\n  limit: int = 50) -> PageParams", "gom tham số dùng chung", VIOLET)]
    for i, (n, code, note, c) in enumerate(items):
        x = 2 + i * 31.5
        col = t["c"][c]
        box(ax, x, 6, 29.5, 34, "", t, color=col, fill=tint(col, t, .08))
        ax.text(x + 2, 36, n, fontsize=8.6, weight="bold", color=col)
        ax.text(x + 2, 30, code, fontsize=6.9, family="monospace", color=t["fg"], va="top")
        ax.text(x + 2, 16, note, fontsize=7.6, color=t["fg2"], va="top")


@figure("dep-cost", size=(8.4, 3.4))
def _(fig, t):
    ax = fig.subplots()
    rows = bench("deps")
    lab = {"async": ("async def", BLUE), "sync": ("def (qua threadpool)", RED), "yield": ("async def + yield", VIOLET),
           "cached": ("1 dependency khai báo k lần (cache)", GREEN)}
    for kind, (l, c) in lab.items():
        rr = [r for r in rows if r["kind"] == kind]
        k = np.array([r["k"] for r in rr]); us = np.array([r["us"] for r in rr])
        slope = np.polyfit(k, us, 1)[0]
        ax.plot(k, us, marker="o", color=t["c"][c], label=f"{l}: ~{slope:.0f} µs/dependency")
    ax.set_xlabel("số dependency nối tiếp k"); ax.set_ylabel("µs / request (trong tiến trình)")
    ax.set_title("Số đo thật: chi phí dependency theo cách khai báo")
    ax.legend(fontsize=8, loc="upper left"); ax.set_xticks([0, 1, 5, 10, 20])
    ygrid(ax, t)


@figure("overrides", size=(8.6, 3.2))
def _(fig, t):
    ax = canvas(fig, (0, 122), (0, 44))
    nodes = [("settings", 4, 22, VIOLET, False), ("db", 30, 22, BLUE, False), ("current_tenant", 56, 30, RED, True),
             ("repo", 84, 22, GREEN, False), ("handler", 104, 22, MAGENTA, False)]
    for n, x, y, c, over in nodes:
        col = t["c"][c]
        box(ax, x, y, 18 if n != "current_tenant" else 22, 7, n, t, color=col, fill=tint(col, t, .15), fs=7.8,
            ls="--" if over else "-")
    box(ax, 56, 10, 22, 7, "fake_tenant()\n→ Tenant(id=99)", t, color=t["c"][GREEN], fill=tint(t["c"][GREEN], t, .2), fs=7.6)
    arrow(ax, 67, 17.3, 67, 29.7, t, color=t["c"][GREEN])
    for (x1, x2, y1, y2) in ((22.3, 29.7, 25.5, 25.5), (48.3, 55.7, 25.5, 33.5), (78.3, 83.7, 33.5, 25.5), (102.3, 103.7, 25.5, 25.5)):
        arrow(ax, x1, y1, x2, y2, t, lw=1)
    ax.text(2, 40, "app.dependency_overrides[current_tenant] = fake_tenant", fontsize=8.6, family="monospace", color=t["fg"])
    ax.text(2, 4, "Chỉ nút bị override thay đổi; các nút khác (settings, db) vẫn chạy thật — override theo đúng object hàm",
            fontsize=7.8, color=t["fg2"])


@figure("case", size=(9.4, 3.8))
def _(fig, t):
    ax = canvas(fig, (0, 134), (0, 50))
    nodes = {"get_settings": (2, 30, VIOLET), "get_pool": (2, 12, VIOLET), "db_session\n(yield, scope=function)": (30, 12, BLUE),
             "current_principal\n(JWT, M11)": (30, 32, RED), "current_tenant": (62, 32, ORANGE), "invoice_repo\n(tenant_id cố định)": (62, 12, GREEN),
             "create_invoice": (98, 22, MAGENTA)}
    for n, (x, y, c) in nodes.items():
        col = t["c"][c]
        box(ax, x, y, 26 if "invoice" not in n else 28, 9, n, t, color=col, fill=tint(col, t, .15), fs=7.6)
    E = [((28.3, 34.5), (29.7, 36.5)), ((28.3, 16.5), (29.7, 16.5)), ((56.3, 36.5), (61.7, 36.5)), ((56.3, 16.5), (61.7, 16.5)),
         ((56.3, 18.5), (61.7, 33.5)), ((75, 31.8), (75, 21.3)), ((90.3, 16.5), (97.7, 24)), ((90.3, 36.5), (97.7, 28))]
    for (x1, y1), (x2, y2) in E:
        arrow(ax, x1, y1, x2, y2, t, lw=1)
    ax.text(2, 46, "Đồ thị dependency của invoice-api: toàn async def (~50 µs), một session cho cả request", fontsize=9,
            weight="bold", color=t["fg"])
    ax.text(98, 12, "commit trước khi\ntrả 201", fontsize=7.6, color=t["fg2"], va="top")


if __name__ == "__main__":
    run("08")
