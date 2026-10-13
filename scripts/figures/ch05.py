"""Hình minh họa cho Module 05 — Serialization, JSON Schema & settings."""
import numpy as np
from matplotlib.patches import FancyBboxPatch

from figkit import (AQUA, BLUE, GREEN, MAGENTA, ORANGE, RED, VIOLET, YELLOW, arrow, bench, box,
                    canvas, figure, run, tint, xgrid, ygrid)


@figure("dump-modes", size=(9.4, 4.1))
def _(fig, t):
    ax = canvas(fig, (0, 132), (0, 57))
    cb = t["c"][BLUE]
    box(ax, 2, 18, 26, 18, "Inv (object)\nissued_at: datetime\ntotal: Decimal\napi_key: SecretStr", t,
        color=cb, fill=tint(cb, t, .14), fs=7.8)
    outs = [("model_dump()", "{'issued_at': datetime(…UTC),\n 'total': Decimal('118007'),\n 'api_key': SecretStr('**********')}", 38, VIOLET),
            ("model_dump(mode='json')", "{'issued_at': '2026-10-13T04:45:00Z',\n 'total': '118007',\n 'api_key': '**********'}", 21, AQUA),
            ("model_dump_json()", '{"issued_at":"2026-10-13T04:45:00Z",\n "total":"118007","api_key":"**********"}', 4, GREEN)]
    for name, body, y, c in outs:
        col = t["c"][c]
        arrow(ax, 28.3, 27, 39.7, y + 6, t, color=col)
        box(ax, 40, y, 30, 12, name, t, color=col, fill=tint(col, t, .16), fs=8.2, weight="bold")
        ax.text(73, y + 6, body, fontsize=7.4, family="monospace", va="center", color=t["fg"])
    ax.text(2, 54, "Một model, ba biểu diễn (đã chạy thật)", fontsize=9.4, weight="bold", color=t["fg"])
    ax.text(2, 12, "JSON: Decimal → chuỗi\ndatetime → ISO 8601\nSecretStr → che", fontsize=7.8, color=t["fg2"], va="top")


@figure("roundtrip", size=(9.0, 3.8))
def _(fig, t):
    ax = canvas(fig, (0, 128), (0, 52))
    cr, cg = t["c"][RED], t["c"][GREEN]
    ax.text(2, 49, "Bẫy round-trip: computed_field + extra='forbid'", fontsize=9.2, weight="bold", color=cr)
    box(ax, 2, 30, 30, 12, "LineOut(quantity=1.5,\nunit_price=18353)", t, color=t["line"], fs=7.8)
    arrow(ax, 32.3, 36, 41.7, 36, t)
    box(ax, 42, 30, 40, 12, '{"quantity":"1.5","unit_price":18353,\n "amount":27530}', t, color=t["line"], fs=7.6)
    arrow(ax, 82.3, 36, 91.7, 36, t, color=cr)
    box(ax, 92, 30, 34, 12, "LineOut.model_validate_json\n→ ('amount',) extra_forbidden", t, color=cr, fill=tint(cr, t, .12), fs=7.6)
    ax.text(2, 23, "Sửa: tách model vào / ra", fontsize=9.2, weight="bold", color=cg)
    box(ax, 2, 4, 36, 14, "LineIn\nquantity, unit_price, amount\n(không computed field)", t, color=cg, fill=tint(cg, t, .12), fs=7.8)
    box(ax, 46, 4, 36, 14, "LineOut\n+ tax (computed / tính sẵn)\nchỉ dùng để xuất", t, color=t["c"][BLUE], fill=tint(t["c"][BLUE], t, .12), fs=7.8)
    ax.text(88, 11, "đọc lại dữ liệu đã xuất:\nexclude computed field, hoặc\nmodel đọc có extra='ignore'", fontsize=7.8, color=t["fg2"], va="center")


@figure("alias", size=(9.0, 3.6))
def _(fig, t):
    ax = canvas(fig, (0, 128), (0, 50))
    cb = t["c"][BLUE]
    ins = ['{"taxCode": …}  (API mới, camelCase)', '{"tax_code": …}  (validate_by_name)', '{"mst": …}  (hệ thống cũ)',
           '{"seller": {"tax_code": …}}  (AliasPath)']
    for i, s in enumerate(ins):
        y = 38 - i * 9
        box(ax, 2, y, 44, 7, s, t, color=t["line"], fs=7.6)
        arrow(ax, 46.3, y + 3.5, 55.7, 24, t, color=t["fg2"], lw=1.1)
    box(ax, 56, 18, 24, 12, "field: tax_code\n(Python)", t, color=cb, fill=tint(cb, t, .16), fs=8.4, weight="bold")
    arrow(ax, 80.3, 24, 89.7, 24, t, color=t["c"][GREEN])
    box(ax, 90, 18, 36, 12, '{"taxCode": "0100233488"}\nserialize_by_alias=True', t, color=t["c"][GREEN],
        fill=tint(t["c"][GREEN], t, .12), fs=7.8)
    ax.text(2, 47, "Nhiều tên khi nhận, một tên khi xuất", fontsize=9.2, weight="bold", color=t["fg"])


@figure("schema-modes", size=(8.8, 3.4))
def _(fig, t):
    ax = canvas(fig, (0, 124), (0, 46))
    fields = ["lineNo", "unitPrice", "quantity", "note", "amount"]
    val = {"lineNo": "bắt buộc", "unitPrice": "bắt buộc", "quantity": "bắt buộc · number|string", "note": "tùy chọn", "amount": "—"}
    ser = {"lineNo": "luôn có", "unitPrice": "luôn có", "quantity": "luôn có · string", "note": "có (có thể null)", "amount": "luôn có (computed)"}
    ax.text(4, 41, "trường", fontsize=8.8, weight="bold", color=t["fg"])
    ax.text(32, 41, 'mode="validation" (client gửi gì)', fontsize=8.8, weight="bold", color=t["c"][BLUE])
    ax.text(80, 41, 'mode="serialization" (server trả gì)', fontsize=8.8, weight="bold", color=t["c"][GREEN])
    for i, f in enumerate(fields):
        y = 34 - i * 6.5
        ax.text(4, y, f, fontsize=8.4, family="monospace", color=t["fg"], va="center")
        for x, d, c in ((32, val, BLUE), (80, ser, GREEN)):
            v = d[f]
            col = t["c"][c] if v not in ("—", "tùy chọn") else t["muted"]
            box(ax, x, y - 2.5, 40, 5, v, t, color=col, fill=tint(col, t, .12), fs=7.6)


@figure("schema-diff", size=(9.2, 4.8))
def _(fig, t):
    ax = fig.subplots()
    rows = bench("schema_diff")
    order = ["không đột biến", "trường lạ", "thiếu trường", "thuế suất lạ", "số lượng âm", "số → chuỗi số", "int → float .0",
             "MST có dấu gạch", "MST sai checksum", "amount dòng sai", "lệch tổng 1 đồng", "line_no trùng", "ngày không múi giờ"]
    rows = sorted(rows, key=lambda r: order.index(r["mutation"]))
    cols = ["JSON Schema", "Pydantic lax", "Pydantic strict"]
    for i, r in enumerate(rows):
        js_ok = any(k.startswith("schema nhận") for k in r["lax"])
        lax_ok = any(k.endswith("pydantic nhận") for k in r["lax"])
        st_ok = any(k.endswith("pydantic nhận") for k in r["strict"])
        vals = [js_ok, lax_ok, st_ok]
        disagree = len(set(vals)) > 1
        for j, ok in enumerate(vals):
            c = t["c"][GREEN] if ok else t["muted"]
            if disagree and ok and j == 0 and not st_ok:
                c = t["c"][YELLOW]
            if disagree and ok and j == 1 and not js_ok:
                c = t["c"][YELLOW]
            ax.add_patch(FancyBboxPatch((j + 0.06, i + 0.1), 0.88, 0.8, boxstyle="round,pad=0,rounding_size=0.08",
                                        fc=tint(c, t, .3), ec=c, lw=0.9))
            ax.text(j + 0.5, i + 0.5, "nhận" if ok else "từ chối", ha="center", va="center", fontsize=8, color=t["fg"])
    ax.set_xlim(0, 3); ax.set_ylim(len(rows), 0)
    ax.set_xticks(np.arange(3) + 0.5, cols); ax.xaxis.tick_top()
    ax.set_yticks(np.arange(len(rows)) + 0.5, [r["mutation"] for r in rows], fontsize=8.2)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    ax.set_title("Thí nghiệm: 13 loại đột biến × 40 lần (kết quả mỗi loại nhất quán) — vàng: nhận trong khi bên kia từ chối",
                 pad=22, fontsize=8.8)


@figure("ser-cost", size=(8.6, 3.4))
def _(fig, t):
    ax = fig.subplots()
    rows = bench("misc")["ser"]
    cases = [("model_dump() + json.dumps", RED), ("model_dump(mode='json') + orjson", ORANGE),
             ("model_dump_json()", BLUE), ("model_dump() (python)", t["muted"]), ("msgspec.json.encode", GREEN)]
    for name, c in cases:
        rr = [r for r in rows if r["case"] == name]
        col = t["c"][c] if isinstance(c, int) else c
        ax.plot([r["lines"] for r in rr], [r["us"] for r in rr], marker="o", color=col, label=name,
                ls="--" if "python" in name else "-")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("số dòng hàng của hóa đơn"); ax.set_ylabel("µs / lần serialize (trung vị)")
    ax.set_title("Số đo thật: chi phí serialize theo kích thước hóa đơn")
    ax.legend(fontsize=7.8, loc="upper left")
    ax.grid(color=t["grid"], lw=0.6); ax.set_axisbelow(True)


@figure("settings", size=(8.8, 3.8))
def _(fig, t):
    ax = canvas(fig, (0, 124), (0, 54))
    levels = [("1 · tham số khởi tạo", "Settings(env='prod') → env = 'prod'", VIOLET),
              ("2 · biến môi trường", "INVOICE_DB__POOL_SIZE=20 → pool_size = 20", BLUE),
              ("3 · file .env", "bỏ biến môi trường → pool_size = 15", AQUA),
              ("4 · thư mục secrets", "bỏ .env → jwt_secret đọc từ file", GREEN),
              ("5 · giá trị mặc định", "db.url = postgresql+asyncpg://localhost/…", t["muted"])]
    for i, (n, ex, c) in enumerate(levels):
        y = 42 - i * 9
        col = t["c"][c] if isinstance(c, int) else c
        w = 40 - i * 3
        box(ax, 2 + i * 1.5, y, w, 7, n, t, color=col, fill=tint(col, t, .18), fs=8.2, weight="bold")
        ax.text(48, y + 3.5, ex, fontsize=8, color=t["fg"], va="center", family="monospace")
    ax.text(2, 51, "Thứ tự ưu tiên nguồn của pydantic-settings (kiểm chứng bằng thí nghiệm)", fontsize=9.2,
            weight="bold", color=t["fg"])
    ax.text(48, 2, "repr(settings): jwt_secret=SecretStr('**********')", fontsize=7.8, color=t["fg2"], family="monospace")


@figure("in-out", size=(9.2, 3.8))
def _(fig, t):
    ax = canvas(fig, (0, 130), (0, 54))
    cols = [("InvoiceIn (client gửi)", ["series, number", "seller_tax_code", "buyer", "issued_at", "lines[LineIn]", "totals"], BLUE),
            ("Hàng ORM (database)", ["id, tenant_id", "series, number, …", "lines", "status", "signature_blob", "created_by"], VIOLET),
            ("InvoiceOut (server trả)", ["id", "series, number, …", "lines[LineOut] + tax", "status", "lookup_code", "issued_at (+07:00)"], GREEN)]
    for k, (title, items, c) in enumerate(cols):
        x = 2 + k * 44
        col = t["c"][c]
        box(ax, x, 4, 40, 42, "", t, color=col, fill=tint(col, t, .06))
        ax.text(x + 20, 42, title, ha="center", fontsize=8.6, weight="bold", color=col)
        for i, it in enumerate(items):
            danger = it in ("tenant_id", "signature_blob", "created_by") or "tenant_id" in it or it in ("signature_blob", "created_by")
            ax.text(x + 3, 36 - i * 5.3, it, fontsize=8, color=t["c"][RED] if danger else t["fg"])
    ax.text(2, 50, "Ba hình dạng của cùng một hóa đơn — trường đỏ không bao giờ ra khỏi server", fontsize=9.2,
            weight="bold", color=t["fg"])


if __name__ == "__main__":
    run("05")
