"""Hình minh họa cho Module 15 — Pydantic cho LLM (số liệu: scripts/bench/results/llm.json)."""
import numpy as np

from figkit import (AQUA, BLUE, GREEN, MAGENTA, ORANGE, RED, VIOLET, YELLOW, arrow, bench, box,
                    canvas, figure, run, tint, xgrid, ygrid)


def llm():
    return bench("llm")


@figure("four-ways", size=(9.6, 3.6))
def _(fig, t):
    ax = canvas(fig, (0, 136), (0, 50))
    cols = ["cú pháp JSON", "đúng schema", "đúng nghiệp vụ"]
    rows = [("prompt thuần", [0, 0, 0]), ("JSON mode", [1, 0, 0]), ("schema strict /\nconstrained decoding", [1, 1, 0]),
            ("+ model_validate_json\n(validator Pydantic)", [1, 1, 1])]
    for j, c in enumerate(cols):
        ax.text(58 + j * 26, 44, c, fontsize=8.2, weight="bold", color=t["fg"], ha="center")
    for i, (name, v) in enumerate(rows):
        y = 33 - i * 9
        ax.text(2, y + 3, name, fontsize=7.8, color=t["fg"], va="center")
        for j, ok in enumerate(v):
            c = t["c"][GREEN] if ok else t["c"][RED]
            box(ax, 46 + j * 26, y, 24, 6.5, "đảm bảo" if ok else "không", t, color=c, fill=tint(c, t, .2), fs=7.4)
    ax.text(2, 2, "Grammar không biểu diễn được validator Python (checksum MST, tổng = Σ dòng) → luôn validate sau khi sinh",
            fontsize=7.6, color=t["fg2"])


@figure("masking", size=(9.6, 3.8))
def _(fig, t):
    ax = canvas(fig, (0, 136), (0, 54))
    cb, cg, cr, cv = t["c"][BLUE], t["c"][GREEN], t["c"][RED], t["c"][VIOLET]
    ax.text(2, 50, 'Đã sinh: {"buyer_tax_code": "0312", "vat_rate": "', fontsize=8.4, family="monospace", color=t["fg"])
    box(ax, 2, 30, 26, 12, "LLM forward\n→ logits trên\n~150k token", t, color=cb, fill=tint(cb, t, .12), fs=7.4)
    box(ax, 36, 30, 30, 12, "PDA của schema\n(trạng thái: trong chuỗi\nenum vat_rate)", t, color=cv, fill=tint(cv, t, .12), fs=7.2)
    arrow(ax, 28.3, 36, 35.7, 36, t)
    toks = [("5", 2.1, True), ("8", 1.7, True), ("10", 1.2, True), ("0", 0.4, True), ("5%", 2.6, False),
            ("năm", 1.9, False), ("\"", 1.1, False), ("VAT", 0.8, False)]
    for i, (tok, lg, ok) in enumerate(toks):
        y = 46 - i * 5.4
        c = cg if ok else cr
        ax.text(74, y, f"{tok!r:6s}", fontsize=7.6, family="monospace", color=t["fg"], va="center")
        ax.barh(y, lg * 8, left=84, height=3.6, color=tint(c, t, .5))
        ax.text(84 + lg * 8 + 1, y, f"{lg:.1f}" if ok else f"{lg:.1f} → −∞", fontsize=7, color=c, va="center")
    arrow(ax, 66.3, 36, 73, 36, t)
    ax.text(74, 50.5, "token   logit (ví dụ minh họa)", fontsize=7.2, color=t["fg2"])
    ax.text(2, 22, "Token làm chuỗi thoát khỏi ngôn ngữ của grammar bị che (−∞).\n"
                   "Model 'muốn' viết \"5%\" nhất, nhưng chỉ có thể chọn trong {\"5\", \"8\", \"10\", \"0\"}.",
            fontsize=7.6, color=t["fg2"], va="top")
    ax.text(2, 8, "FSM (regex, Outlines) · pushdown automaton (JSON đệ quy, XGrammar): mask tính trước + cache",
            fontsize=7.4, color=cv)


@figure("modes", size=(9.8, 3.8))
def _(fig, t):
    d = llm()["l1_modes"]
    s = d["summary"]
    ax = fig.subplots()
    modes = [("prompt", "prompt thuần"), ("json", "JSON mode"), ("schema", "ràng buộc theo schema")]
    metrics = [("parse", "parse được JSON", BLUE), ("valid", "hợp lệ Pydantic\n(kể cả checksum MST)", GREEN),
               ("all_fields_correct", "đúng mọi trường\n(người mua, MST, thuế, tổng)", VIOLET)]
    x = np.arange(len(modes))
    w = 0.26
    for j, (k, lab, c) in enumerate(metrics):
        vals = [s[m][k] * 100 for m, _ in modes]
        ax.bar(x + (j - 1) * w, vals, w, color=t["c"][c], label=lab)
        for i, v in enumerate(vals):
            ax.text(i + (j - 1) * w, v + 1.5, f"{v:.0f}%", ha="center", fontsize=7.4, color=t["fg"])
    ax.set_xticks(x, [lab for _, lab in modes])
    ax.set_ylim(0, 115)
    ax.set_ylabel("% trên " + str(d["cases"]) + " tin nhắn")
    ax.set_title(f"Số đo thật (l1): {d['model']} trên CPU, trích hóa đơn nháp từ tin nhắn tiếng Việt")
    ax.legend(fontsize=7.4, loc="upper left", ncols=3)
    ygrid(ax, t)


@figure("overhead", size=(9.0, 3.2))
def _(fig, t):
    o = llm()["l3_overhead"]
    ax1, ax2 = fig.subplots(1, 2)
    ax1.bar(["không ràng buộc", "ràng buộc schema"], [o["ms_per_token_prompt"], o["ms_per_token_schema"]],
            color=[t["c"][BLUE], t["c"][GREEN]])
    for i, v in enumerate([o["ms_per_token_prompt"], o["ms_per_token_schema"]]):
        ax1.text(i, v + 1, f"{v:.0f} ms".replace(".", ","), ha="center", fontsize=8, color=t["fg"])
    ax1.set_ylabel("ms / token (CPU)")
    ax1.set_title("Thời gian sinh mỗi token")
    ygrid(ax1, t)
    ax2.bar(["biên dịch\nschema", "biên dịch\nJSON", "mask p50\n/token", "mask p99\n/token"],
            [o["compile_schema_ms"], o["compile_json_ms"], o["mask_us_p50"] / 1000, o["mask_us_p99"] / 1000],
            color=[t["c"][VIOLET], t["c"][VIOLET], t["c"][ORANGE], t["c"][ORANGE]])
    ax2.set_yscale("log")
    for i, v in enumerate([o["compile_schema_ms"], o["compile_json_ms"], o["mask_us_p50"] / 1000, o["mask_us_p99"] / 1000]):
        ax2.text(i, v * 1.3, f"{v:.3g} ms".replace(".", ","), ha="center", fontsize=7.4, color=t["fg"])
    ax2.set_ylabel("ms (log)")
    ax2.set_title(f"Chi phí của xgrammar (vocab {o['vocab']:,})".replace(",", "."))
    ax2.tick_params(axis="x", labelsize=7.4)
    ygrid(ax2, t)
    fig.suptitle("Số đo thật (l3): ràng buộc gần như miễn phí so với một lượt forward", fontsize=9.4, color=t["fg"])
    fig.tight_layout()


@figure("retry", size=(9.0, 3.4))
def _(fig, t):
    d = llm()["l2_retry"]
    ax = fig.subplots()
    k = np.arange(1, 4)
    meas = np.array(d["valid_by_attempts"]) * 100
    p1 = d["valid_by_attempts"][0]
    indep = (1 - (1 - p1) ** k) * 100
    ax.plot(k, meas, marker="o", color=t["c"][RED], label="đo được (prompt thuần + gửi lại lỗi Pydantic)")
    ax.plot(k, indep, marker="s", ls="--", color=t["c"][BLUE], label=f"lý thuyết nếu độc lập: 1 − (1 − p)^k, p = {p1:.2f}".replace(".", ","))
    sch = llm()["l1_modes"]["summary"]["schema"]["valid"] * 100
    ax.axhline(sch, color=t["c"][GREEN], ls=":", lw=1.5)
    ax.text(3.0, sch - 6, f"ràng buộc theo schema, 1 lần gọi: {sch:.0f}%", fontsize=7.6, color=t["c"][GREEN], ha="right")
    for x, y in zip(k, meas):
        ax.text(x, y + 3, f"{y:.0f}%", ha="center", fontsize=7.6, color=t["c"][RED])
    ax.set_xticks(k)
    ax.set_xlabel("số lần gọi tối đa k")
    ax.set_ylabel("% hợp lệ")
    ax.set_ylim(0, 110)
    ax.set_title("Số đo thật (l2): validate–retry — lỗi có tương quan, retry kém hơn lý thuyết")
    ax.legend(fontsize=7.4, loc="center right")
    ygrid(ax, t)


@figure("partial", size=(9.8, 3.6))
def _(fig, t):
    d = llm()["l4_partial"]
    ax = canvas(fig, (0, 140), (0, 50))
    ax.text(2, 47, "Số đo thật (l4): validate tiền tố JSON khi LLM đang sinh (experimental_allow_partial)", fontsize=9,
            weight="bold", color=t["fg"])
    keys = list(d.keys())
    for col, k in enumerate(keys):
        r = d[k]
        x = 2 + col * 70
        c = t["c"][RED] if "bắt buộc" in k else t["c"][GREEN]
        ax.text(x, 41, k, fontsize=8, weight="bold", color=c)
        ax.text(x, 37, f"{r['ok_fraction']:.0%} tiền tố validate được · validate lại mọi ký tự: "
                       f"{r['validate_every_char_total_ms']:.1f} ms".replace(".", ","), fontsize=7.2, color=t["fg2"])
        for i, smp in enumerate(r["samples"][:4]):
            y = 30 - i * 7.5
            res = smp["result"]
            txt = res if isinstance(res, str) else ", ".join(
                f"{kk}" + ("" if kk != "lines" else f"[{len(vv)}]") for kk, vv in res.items())
            box(ax, x, y - 2.2, 66, 6.4, "", t, color=c, fill=tint(c, t, .08))
            ax.text(x + 1.2, y + 1.6, f"{smp['chars']} ký tự", fontsize=6.8, color=t["fg2"])
            ax.text(x + 14, y + 1.6, (txt if len(txt) < 62 else txt[:60] + "…"), fontsize=6.8, color=t["fg"],
                    family="monospace")
            ax.text(x + 1.2, y - 1.0, "…" + smp["prefix"][-46:], fontsize=6.2, color=t["fg2"], family="monospace")


@figure("tools", size=(9.6, 3.4))
def _(fig, t):
    ax = canvas(fig, (0, 136), (0, 46))
    cb, cg, co, cv, cr = (t["c"][k] for k in (BLUE, GREEN, ORANGE, VIOLET, RED))
    box(ax, 2, 18, 26, 14, "def tra_cuu_hoa_don(\n  tax_code: …pattern,\n  period: …,\n  status: Literal[…])",
        t, color=cb, fill=tint(cb, t, .1), fs=6.8)
    box(ax, 36, 26, 28, 10, "TypeAdapter(f).json_schema()\n→ mô tả tool / MCP inputSchema", t, color=cv,
        fill=tint(cv, t, .12), fs=7)
    box(ax, 72, 26, 22, 10, "LLM chọn tool\n+ đối số JSON", t, color=co, fill=tint(co, t, .12), fs=7.2)
    box(ax, 72, 6, 22, 12, "@validate_call\nkiểm đối số", t, color=cg, fill=tint(cg, t, .14), fs=7.4)
    box(ax, 104, 12, 30, 10, "chạy hàm (chỉ đọc,\nphạm vi tenant)", t, color=cg, fill=tint(cg, t, .12), fs=7.2)
    box(ax, 36, 6, 28, 10, "ValidationError →\ntool result cho LLM sửa", t, color=cr, fill=tint(cr, t, .12), fs=7)
    arrow(ax, 28.3, 27, 35.7, 31, t)
    arrow(ax, 64.3, 31, 71.7, 31, t)
    arrow(ax, 83, 25.7, 83, 18.3, t)
    arrow(ax, 94.3, 14, 103.7, 16, t, color=cg)
    arrow(ax, 71.7, 11, 64.3, 11, t, color=cr)
    ax.text(2, 42, "Một nguồn sự thật — chữ ký hàm có kiểu — sinh cả mô tả tool lẫn kiểm tra đối số", fontsize=9,
            weight="bold", color=t["fg"])


@figure("security", size=(9.6, 3.6))
def _(fig, t):
    ax = canvas(fig, (0, 136), (0, 50))
    layers = [("email khách (có thể chứa\nprompt injection)", RED), ("LLM", ORANGE),
              ("hình dạng: constrained\ndecoding + model_validate_json", BLUE),
              ("miền giá trị: Literal hành động,\nmax_length, pattern", BLUE),
              ("nghiệp vụ: MST, hóa đơn\nthuộc tenant (RLS)", VIOLET), ("người duyệt (CS)", GREEN)]
    for i, (s, c) in enumerate(layers):
        x = 2 + i * 22.4
        col = t["c"][c]
        box(ax, x, 18, 20.5, 16, s, t, color=col, fill=tint(col, t, .12), fs=6.8)
        if i < len(layers) - 1:
            arrow(ax, x + 20.7, 26, x + 22.2, 26, t, lw=1)
    ax.text(2, 45, "Output LLM là input không tin cậy — nhiều lớp, mỗi lớp chặn một loại lỗi", fontsize=9,
            weight="bold", color=t["fg"])
    ax.text(2, 11, "OWASP LLM Top 10 (2025): LLM01 Prompt Injection · LLM05 Improper Output Handling · "
                   "tool chỉ đọc, không có hành động 'refund'", fontsize=7.4, color=t["fg2"])


@figure("pipeline", size=(9.8, 3.6))
def _(fig, t):
    ax = canvas(fig, (0, 140), (0, 50))
    steps = [("phân loại ticket", "schema strict\nLiteral 12 loại", GREEN),
             ("trích hóa đơn nháp", "constrained theo\nInvoiceDraft", GREEN),
             ("soạn câu trả lời", "tự do (reasoning\ntrước) → trích xuất", ORANGE),
             ("validate–retry", "≤ 3 lần, lỗi Pydantic,\nretry budget 10%", VIOLET),
             ("SSE", "DraftPreview (partial)\n→ InvoiceDraft (final)", BLUE),
             ("CS duyệt", "người quyết định\ngửi khách", GREEN)]
    for i, (h, s, c) in enumerate(steps):
        x = 2 + i * 23
        col = t["c"][c]
        box(ax, x, 16, 21, 20, "", t, color=col, fill=tint(col, t, .1))
        ax.text(x + 10.5, 31.5, h, fontsize=7.8, weight="bold", color=col, ha="center")
        ax.text(x + 10.5, 23.5, s, fontsize=6.6, color=t["fg"], ha="center", va="center")
        if i < len(steps) - 1:
            arrow(ax, x + 21.2, 26, x + 22.8, 26, t, lw=1)
    ax.text(2, 45, "Pipeline draft của ai-gateway", fontsize=9, weight="bold", color=t["fg"])
    ax.text(2, 9, "mỗi lời gọi LLM có span: model, token in/out, số lần retry, kết quả validate (Module 13)",
            fontsize=7.4, color=t["fg2"])


if __name__ == "__main__":
    run("15")
