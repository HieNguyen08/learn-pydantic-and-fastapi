"""Hình minh họa cho Module 13 — Production & observability (số liệu: scripts/bench/results/production.json)."""
import numpy as np
from matplotlib.patches import Rectangle

from figkit import (AQUA, BLUE, GREEN, MAGENTA, ORANGE, RED, VIOLET, YELLOW, arrow, bench, box,
                    canvas, figure, run, tint, xgrid, ygrid)


def prod():
    return bench("production")


@figure("process", size=(9.6, 3.8))
def _(fig, t):
    ax = canvas(fig, (0, 136), (0, 52))
    cb, cg, co, cv = t["c"][BLUE], t["c"][GREEN], t["c"][ORANGE], t["c"][VIOLET]
    ax.text(2, 48, "1 Uvicorn / pod (khuyên dùng trên Kubernetes)", fontsize=8.8, weight="bold", color=cg)
    box(ax, 2, 36, 22, 7, "Service / LB", t, color=t["line"], fs=7.6)
    for i in range(4):
        x = 2 + i * 16
        box(ax, x, 8, 14, 20, "", t, color=cg, fill=tint(cg, t, .08))
        ax.text(x + 7, 25, f"pod {i + 1}", fontsize=7.2, color=cg, ha="center")
        box(ax, x + 1.5, 11, 11, 9, "uvicorn\n1 vCPU\npool=5", t, color=cb, fill=tint(cb, t, .15), fs=6.4)
        arrow(ax, 13, 35.7, x + 7, 28.3, t, lw=0.9)
    ax.text(2, 3, "probe thấy đúng tiến trình · HPA scale từng pod · tổng kết nối DB = số pod × 5", fontsize=7.2,
            color=t["fg2"])
    ax.plot([70, 70], [2, 50], color=t["grid"], lw=1)
    ax.text(74, 48, "N worker / pod (máy ảo, không có orchestrator)", fontsize=8.8, weight="bold", color=co)
    box(ax, 74, 36, 22, 7, "LB", t, color=t["line"], fs=7.6)
    box(ax, 74, 8, 60, 20, "", t, color=co, fill=tint(co, t, .08))
    ax.text(104, 25, "1 pod / VM: gunicorn hoặc uvicorn --workers 4", fontsize=7.2, color=co, ha="center")
    for i in range(4):
        box(ax, 76 + i * 14.5, 11, 12.5, 9, f"worker {i + 1}\npool=5", t, color=cb, fill=tint(cb, t, .15), fs=6.4)
    arrow(ax, 85, 35.7, 100, 28.3, t, lw=0.9)
    ax.text(74, 3, "probe chỉ tới một worker bất kỳ · tổng kết nối = N × pool", fontsize=7.2, color=t["fg2"])


@figure("probes", size=(9.6, 3.6))
def _(fig, t):
    ax = canvas(fig, (0, 136), (0, 50))
    cb, cg, co, cr = t["c"][BLUE], t["c"][GREEN], t["c"][ORANGE], t["c"][RED]
    cols = [("startup", "đã khởi động xong?\n(nạp cache, kiểm schema)", "chưa → chưa chạy 2 probe kia;\nquá hạn → khởi động lại", VIOLET),
            ("liveness", "tiến trình còn tự hồi phục\nđược không? (event loop)", "thất bại → KHỞI ĐỘNG LẠI\ncontainer", RED),
            ("readiness", "có nên nhận traffic?\n(pool DB, Redis, đang tắt?)", "thất bại → RÚT khỏi LB\n(không khởi động lại)", GREEN)]
    for i, (n, q, a, c) in enumerate(cols):
        x = 2 + i * 45
        col = t["c"][c]
        box(ax, x, 6, 42, 36, "", t, color=col, fill=tint(col, t, .08))
        ax.text(x + 21, 38, n, fontsize=9, weight="bold", color=col, ha="center")
        ax.text(x + 21, 30, q, fontsize=7.4, color=t["fg"], ha="center", va="center")
        ax.text(x + 21, 17, a, fontsize=7.4, color=col, ha="center", va="center")
    ax.text(2, 46, "Ba probe, ba câu hỏi khác nhau — phụ thuộc ngoài (DB) chỉ thuộc readiness", fontsize=9,
            weight="bold", color=t["fg"])
    ax.text(68, 10, "✗ đừng kiểm DB ở đây: DB chậm → mọi pod restart", fontsize=6.8, color=cr, ha="center")


@figure("shutdown", size=(9.8, 3.8))
def _(fig, t):
    ax = canvas(fig, (0, 140), (0, 52))
    cr, cg, cv, co, cb = t["c"][RED], t["c"][GREEN], t["c"][VIOLET], t["c"][ORANGE], t["c"][BLUE]
    xs = lambda s: 10 + s * 4.0         # 1 s = 4 đơn vị
    ax.plot([xs(0), xs(30)], [30, 30], color=t["fg2"], lw=1)
    for s in (0, 8, 28, 30):
        ax.plot([xs(s), xs(s)], [29, 31], color=t["fg2"], lw=1)
        ax.text(xs(s), 26.5, f"{s} s", fontsize=7, color=t["fg2"], ha="center")
    ax.add_patch(Rectangle((xs(0), 32), xs(8) - xs(0), 6, color=tint(cv, t, .3)))
    ax.text(xs(4), 35, "preStop: sleep 8\n(vẫn phục vụ; LB rút pod)", fontsize=7, ha="center", va="center", color=t["fg"])
    ax.add_patch(Rectangle((xs(8), 32), xs(28) - xs(8), 6, color=tint(cb, t, .25)))
    ax.text(xs(18), 35, "SIGTERM → uvicorn đóng socket, chờ request dở dang (≤ 20 s)\n→ lifespan: đóng pool, flush telemetry",
            fontsize=7, ha="center", va="center", color=t["fg"])
    ax.add_patch(Rectangle((xs(28), 32), xs(30) - xs(28), 6, color=tint(cr, t, .3)))
    ax.text(xs(30) + 1, 35, "SIGKILL nếu\nchưa thoát", fontsize=7, color=cr, va="center")
    ax.text(xs(0), 42, "xóa pod: Kubernetes ĐỒNG THỜI bắt đầu preStop và cập nhật EndpointSlice (bất đồng bộ, vài giây)",
            fontsize=7.4, color=t["fg2"])
    r = prod()["p1_graceful"]
    ax.text(2, 18, "Số đo thật (p1): 10 request dài 2 s đang chạy + 10 request mới đến 0,3 s sau SIGTERM", fontsize=7.8,
            weight="bold", color=t["fg"])
    for i, x in enumerate(r):
        ax.text(4, 12 - i * 5, f"{x['config']}: đang chạy {x['inflight_ok']}/10 xong · đến sau SIGTERM "
                               f"{x['after_ok']}/10 ok ({', '.join(x['errors'])})", fontsize=7.4,
                color=cg if x["inflight_ok"] == 10 else cr)
    ax.text(2, 49, "Graceful shutdown trên Kubernetes", fontsize=9, weight="bold", color=t["fg"])


@figure("pillars", size=(9.6, 3.8))
def _(fig, t):
    ax = canvas(fig, (0, 136), (0, 52))
    cb, cg, co, cv = t["c"][BLUE], t["c"][GREEN], t["c"][ORANGE], t["c"][VIOLET]
    box(ax, 2, 30, 38, 14, "METRIC\nhistogram p99 /v1/invoices\n= 420 ms (vượt SLO)", t, color=cb,
        fill=tint(cb, t, .12), fs=7.6)
    box(ax, 49, 30, 38, 14, "TRACE (trace_id 4bf9…)\nserver 410 ms\n└ db: INSERT 380 ms", t, color=cv,
        fill=tint(cv, t, .12), fs=7.6)
    box(ax, 96, 30, 38, 14, "LOG (JSON)\n{\"trace_id\":\"4bf9…\",\"tenant\":7,\n\"msg\":\"lock wait 370ms\"}", t,
        color=co, fill=tint(co, t, .12), fs=7.2)
    arrow(ax, 40.3, 37, 48.7, 37, t, color=t["fg2"])
    arrow(ax, 87.3, 37, 95.7, 37, t, color=t["fg2"])
    ax.text(44.5, 40, "exemplar", fontsize=6.8, color=t["fg2"], ha="center")
    ax.text(91.5, 40, "trace_id", fontsize=6.8, color=t["fg2"], ha="center")
    rows = [("rẻ, không phụ thuộc lưu lượng", "theo lưu lượng, lấy mẫu", "đắt nhất, theo lưu lượng"),
            ("“hệ thống có khỏe không?”", "“request này chậm ở đâu?”", "“chính xác chuyện gì xảy ra?”")]
    for j, row in enumerate(rows):
        for i, s in enumerate(row):
            ax.text(21 + i * 47, 24 - j * 6, s, fontsize=7.2, color=t["fg2"], ha="center")
    ax.text(2, 48, "Ba trụ quan sát và sợi chỉ nối chúng: exemplar → trace_id → log", fontsize=9, weight="bold",
            color=t["fg"])
    ax.text(2, 6, "W3C traceparent truyền trace_id qua mọi dịch vụ; mọi dòng log mang trace_id + tenant_id",
            fontsize=7.4, color=t["fg2"])


@figure("obs-cost", size=(9.0, 3.4))
def _(fig, t):
    rows = prod()["p5_observability"]["rows"]
    base = rows[0]["us"]
    ax = fig.subplots()
    labels = ["không quan sát", "+ log JSON\n1 dòng", "+ histogram\nPrometheus", "+ OTel: span\nserver",
              "+ OTel: operation\nspans (mặc định)", "+ operation spans\nlấy mẫu 10%"]
    cols = [t["c"][GREEN], t["c"][ORANGE], t["c"][GREEN], t["c"][BLUE], t["c"][RED], t["c"][MAGENTA]]
    vals = [r["us"] for r in rows]
    ax.bar(range(len(vals)), vals, color=cols)
    for i, v in enumerate(vals):
        ax.text(i, v + 4, f"{v:.0f}" + ("" if i == 0 else f"\n(+{v - base:.0f})"), ha="center", fontsize=7.4,
                color=t["fg"])
    ax.axhline(base, color=t["fg2"], ls=":", lw=1)
    ax.set_xticks(range(len(vals)), labels, fontsize=7.2)
    ax.set_ylabel("µs / request (trong tiến trình)")
    ax.set_ylim(0, max(vals) * 1.25)
    ax.set_title("Số đo thật (p5): chi phí quan sát cho POST hóa đơn 12 dòng")
    ygrid(ax, t)


@figure("percentiles", size=(9.8, 3.6))
def _(fig, t):
    d = prod()["p4_percentiles"]
    ax1, ax2 = fig.subplots(1, 2, gridspec_kw=dict(width_ratios=[1.3, 1]))
    cols = {"pod-a": BLUE, "pod-b": AQUA, "pod-c": VIOLET, "pod-d": RED}
    bins = np.linspace(0, 450, 91)
    for k, xs in d["samples_hist"].items():
        ax1.hist(xs, bins=bins, histtype="step", color=t["c"][cols[k]], lw=1.3, density=True,
                 label=f"{k}: p99 {d['per_pod_p99'][k]:.0f} ms")
    ax1.set_xlabel("latency (ms)")
    ax1.set_yticks([])
    ax1.set_title("Phân phối latency của 4 pod (pod-d nóng)")
    ax1.legend(fontsize=7.4)
    names = ["trung bình\ncác p99", "p99 thật\n(gộp mẫu)", "histogram\nbucket\nmặc định",
             "histogram\nbucket\nquanh SLO"]
    vals = [d["avg_of_p99"], d["true_p99"], d["hist_default"], d["hist_tuned"]]
    c2 = [t["c"][RED], t["c"][GREEN], t["c"][ORANGE], t["c"][GREEN]]
    ax2.bar(range(4), vals, color=c2)
    for i, v in enumerate(vals):
        ax2.text(i, v + 4, f"{v:.0f} ms", ha="center", fontsize=7.6, color=t["fg"])
    ax2.set_xticks(range(4), names, fontsize=6.8)
    ax2.set_ylim(0, 270)
    ax2.set_title("Cùng dữ liệu, bốn con số p99")
    ygrid(ax2, t)
    fig.suptitle("Số đo (p4): đừng lấy trung bình percentile; bucket quyết định độ chính xác", fontsize=9.4,
                 color=t["fg"])
    fig.tight_layout()


@figure("slo", size=(9.0, 3.4))
def _(fig, t):
    ax = fig.subplots()
    hours = np.linspace(0, 720, 721)
    for br, c, lab in ((1, GREEN, "burn rate 1: hết đúng sau 30 ngày → ticket"),
                       (6, ORANGE, "burn rate 6: 5% trong 6 h → gọi trực"),
                       (14.4, RED, "burn rate 14,4: 2% trong 1 h → gọi trực")):
        used = np.minimum(100, br * hours / 720 * 100)
        ax.plot(hours / 24, 100 - used, color=t["c"][c], label=lab)
    ax.set_xlabel("ngày trong cửa sổ SLO 30 ngày")
    ax.set_ylabel("error budget còn lại (%)")
    ax.set_title("SLO 99,9% / 30 ngày cho invoice-api: budget = 54.000 request hỏng ≈ 43 phút sập")
    ax.set_ylim(0, 105)
    ax.legend(fontsize=7.8, loc="lower left")
    ygrid(ax, t)


@figure("backoff", size=(9.8, 3.4))
def _(fig, t):
    d = prod()["p2_backoff"]["rows"]
    ax1, ax2 = fig.subplots(1, 2)
    names = ["retry ngay", "exp., không\njitter", "full\njitter", "equal\njitter", "decorrelated\njitter"]
    cols = [t["c"][ORANGE], t["c"][RED], t["c"][GREEN], t["c"][GREEN], t["c"][GREEN]]
    ax1.bar(names, [r["calls_per_client"] for r in d], color=cols)
    ax1.set_yscale("log")
    for i, r in enumerate(d):
        ax1.text(i, r["calls_per_client"] * 1.15, f"{r['calls_per_client']:.1f}".replace(".", ","), ha="center",
                 fontsize=7.4, color=t["fg"])
    ax1.set_ylabel("lần gọi / client (log)")
    ax1.set_title("Tải tạo ra")
    ax1.tick_params(axis="x", labelsize=7)
    ygrid(ax1, t)
    ax2.bar(names, [r["all_done_s"] for r in d], color=cols)
    ax2.set_yscale("log")
    for i, r in enumerate(d):
        ax2.text(i, r["all_done_s"] * 1.15, f"{r['all_done_s']:.2f} s".replace(".", ","), ha="center", fontsize=7.4,
                 color=t["fg"])
    ax2.set_ylabel("tất cả xong sau (s, log)")
    ax2.set_title("Thời gian hoàn thành")
    ax2.tick_params(axis="x", labelsize=7)
    ygrid(ax2, t)
    fig.suptitle("Mô phỏng (p2): 100 client tranh một tài nguyên 2 lần gọi / 10 ms", fontsize=9.4, color=t["fg"])
    fig.tight_layout()


@figure("metastable", size=(9.8, 3.8))
def _(fig, t):
    d = prod()["p3_metastable"]
    ax = fig.subplots()
    lab = {"none": ("không retry", BLUE), "retry": ("retry 3 lần, không chờ", RED),
           "retry_backoff_budget": ("retry + backoff + jitter + budget 10%", GREEN),
           "shed": ("load shedding", VIOLET)}
    for k, (l, c) in lab.items():
        g = np.array(d[k]["goodput"], dtype=float)
        sm = np.convolve(g, np.ones(3) / 3, mode="same")
        ax.plot(np.arange(len(g)), sm, color=t["c"][c], label=l, lw=1.6)
    r = np.array(d["retry"]["offered"], dtype=float)
    ax.plot(np.arange(len(r)), np.convolve(r, np.ones(3) / 3, mode="same"), color=t["c"][RED], ls=":", lw=1.2,
            label="tải gửi tới (retry không chờ)")
    ax.axvspan(30, 40, color=t["c"][ORANGE], alpha=0.15)
    ax.text(35, 330, "sự cố: năng lực\n100 → 40 req/s", fontsize=7.4, color=t["c"][ORANGE], ha="center", va="top")
    ax.text(62, 12, "retry không chờ: goodput = 0 từ giây ~34 trở đi", fontsize=7.4, color=t["c"][RED])
    ax.axhline(100, color=t["fg2"], ls="--", lw=0.8)
    ax.text(118, 104, "năng lực 100/s", fontsize=7, color=t["fg2"], ha="right")
    ax.set_xlabel("thời gian (s)")
    ax.set_ylabel("req/s")
    ax.set_ylim(0, 340)
    ax.set_title("Mô phỏng (p3): metastable failure — sự cố hết ở giây 40, retry giữ hệ thống ở trạng thái hỏng")
    ax.legend(fontsize=7.4, loc="upper right")
    ygrid(ax, t)


@figure("shedding", size=(9.8, 3.6))
def _(fig, t):
    rows = [r for r in prod()["p6_load_shedding"]["rows"] if r["rate"] == 300]
    ax1, ax2 = fig.subplots(1, 2, gridspec_kw=dict(width_ratios=[1.25, 1]))
    names = ["không giới hạn", "uvicorn\n--limit-concurrency 20", "ASGI middleware\n≤ 20 in-flight"]
    x = np.arange(len(rows))
    ok = np.array([r["ok"] for r in rows]) / 20
    shed = np.array([r["shed"] for r in rows]) / 20
    to = np.array([r["timeout"] for r in rows]) / 20
    ax1.bar(x, ok, color=t["c"][GREEN], label="thành công (goodput)")
    ax1.bar(x, shed, bottom=ok, color=t["c"][ORANGE], label="503 ngay (Retry-After)")
    ax1.bar(x, to, bottom=ok + shed, color=t["c"][RED], label="timeout sau 1 s")
    for i in range(len(rows)):
        ax1.text(i, ok[i] / 2, f"{ok[i]:.0f}/s", ha="center", fontsize=7.6, color="white")
    ax1.set_xticks(x, names, fontsize=7.2)
    ax1.set_ylabel("req/s (tải gửi 300/s)")
    ax1.set_ylim(0, 330)
    ax1.set_title("Kết cục của request")
    ax1.legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncols=3)
    ygrid(ax1, t)
    ax2.bar(x - 0.2, [r["p50"] for r in rows], 0.4, color=t["c"][BLUE], label="p50")
    ax2.bar(x + 0.2, [r["p99"] for r in rows], 0.4, color=t["c"][VIOLET], label="p99")
    ax2.set_xticks(x, names, fontsize=7.2)
    ax2.set_ylabel("ms (request thành công)")
    ax2.set_title("Latency của request thành công")
    ax2.legend(fontsize=7.6)
    ygrid(ax2, t)
    fig.suptitle("Số đo thật (p6): uvicorn, endpoint ~4 ms CPU (năng lực ~200/s), tải open-loop 300/s trong 20 s",
                 fontsize=9.4, color=t["fg"])
    fig.tight_layout()


if __name__ == "__main__":
    run("13")
