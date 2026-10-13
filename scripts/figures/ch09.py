"""Hình minh họa cho Module 09 — Async, đồng thời & hiệu năng."""
import numpy as np

from figkit import (AQUA, BLUE, GREEN, MAGENTA, ORANGE, RED, VIOLET, YELLOW, arrow, bench, box,
                    canvas, figure, run, tint, xgrid, ygrid)


def conc():
    return bench("concurrency")


@figure("e1", size=(9.4, 3.6))
def _(fig, t):
    a1, a2 = fig.subplots(1, 2, gridspec_kw=dict(wspace=0.3))
    rows = conc()["e1_io_modes"]
    spec = [("async", "async def + await", BLUE), ("sync", "def (threadpool 40)", ORANGE), ("blocking", "async def + time.sleep", RED)]
    for ep, lab, c in spec:
        rr = [r for r in rows if r["endpoint"] == ep]
        C = [r["concurrency"] for r in rr]
        a1.plot(C, [r["rps"] for r in rr], marker="o", color=t["c"][c], label=lab)
        a2.plot(C, [r["p50"] for r in rr], marker="o", color=t["c"][c], label=lab)
    a1.axhline(40 / 0.052, color=t["c"][ORANGE], ls=":", lw=1.2)
    a1.text(1.1, 40 / 0.052 * 1.12, "Little: 40 luồng / 52 ms ≈ 770", fontsize=7.6, color=t["c"][ORANGE])
    a1.axhline(1 / 0.0513, color=t["c"][RED], ls=":", lw=1.2)
    a1.text(1.1, 1 / 0.0513 * 1.15, "1 loop / 51 ms ≈ 19,5", fontsize=7.6, color=t["c"][RED])
    for a in (a1, a2):
        a.set_xscale("log"); a.set_yscale("log"); a.set_xlabel("số kết nối đồng thời C")
        a.grid(color=t["grid"], lw=0.6); a.set_axisbelow(True)
    a1.set_ylabel("request/giây"); a1.set_title("Throughput (chờ I/O 50 ms)")
    a2.set_ylabel("p50 (ms)"); a2.set_title("Latency trung vị")
    a1.legend(fontsize=7.6, loc="upper left")


@figure("e2", size=(8.2, 2.9))
def _(fig, t):
    ax = fig.subplots()
    rows = conc()["e2_head_of_line"]
    lab = {"none": "không có tải nền", "async": "20 kết nối → /io/async", "blocking": "20 kết nối → /io/blocking"}
    y = np.arange(len(rows))
    for i, r in enumerate(rows):
        c = t["c"][RED] if r["background"] == "blocking" else t["c"][GREEN]
        ax.barh(i - 0.17, r["p50"], 0.32, color=c)
        ax.barh(i + 0.17, r["p99"], 0.32, color=tint(c, t, .5))
        ax.text(r["p99"] * 1.3, i, f"p50 {r['p50']:.2f} ms · p99 {r['p99']:.1f} ms", va="center", fontsize=8, color=t["fg"])
    ax.set_xscale("log"); ax.set_xlim(0.1, 1e5)
    ax.set_yticks(y, [lab[r["background"]] for r in rows]); ax.invert_yaxis()
    ax.set_xlabel("latency của GET /health (ms, thang log) — đậm: p50, nhạt: p99")
    ax.set_title("Số đo thật: một endpoint chặn làm /health chậm ~2.400 lần")
    xgrid(ax, t)


@figure("e6", size=(7.6, 3.0))
def _(fig, t):
    ax = fig.subplots()
    rows = conc()["e6_threads"]
    for th, c in ((40, ORANGE), (100, GREEN)):
        rr = [r for r in rows if r["threads"] == th]
        ax.plot([r["concurrency"] for r in rr], [r["rps"] for r in rr], marker="o", color=t["c"][c], label=f"{th} luồng")
        ax.axhline(th / 0.065, color=t["c"][c], ls=":", lw=1.1)
        ax.text(21, th / 0.065 * 1.03, f"Little: {th} / 65 ms ≈ {th / 0.065:,.0f}".replace(",", "."), fontsize=7.6, color=t["c"][c])
    ax.set_xscale("log"); ax.set_xlabel("số kết nối đồng thời C"); ax.set_ylabel("request/giây")
    ax.set_title("Số đo thật: endpoint def chờ 50 ms, giới hạn threadpool 40 so với 100")
    ax.legend(fontsize=8, loc="lower right"); ax.set_ylim(0, 1800)
    ygrid(ax, t)


def _mdl(S, rho, n=200000, seed=3, delta=0.0):
    rng = np.random.default_rng(seed)
    lam = rho / S
    inter = rng.exponential(1 / lam, n)
    w = np.zeros(n)
    for i in range(1, n):
        w[i] = max(0.0, w[i - 1] + S - inter[i])     # Lindley: thời gian chờ của khách i
    return w + S + delta


@figure("e4", size=(8.0, 3.2))
def _(fig, t):
    ax = fig.subplots()
    rows = conc()["e4_open_loop"]
    mu = rows[0]["mu"]
    rho = [r["rps"] / mu for r in rows]
    ax.plot(rho, [r["mean"] for r in rows], marker="o", color=t["c"][BLUE], label="trung bình")
    ax.plot(rho, [r["p50"] for r in rows], marker="s", color=t["c"][AQUA], label="p50")
    ax.plot(rho, [r["p99"] for r in rows], marker="^", color=t["c"][RED], label="p99")
    ax.axvspan(0.7, 1.0, color=tint(t["c"][RED], t, .12), lw=0)
    ax.text(0.71, 70, "vùng nguy hiểm\nρ > 0,7", fontsize=8, color=t["c"][RED])
    ax.set_xlim(0.15, 1.0); ax.set_xlabel("utilization ρ = λ / μ (μ ≈ 402 req/s)"); ax.set_ylabel("latency (ms)")
    ax.set_title("Số đo thật, open-loop: latency theo mức tải (endpoint 2 ms CPU)")
    ax.legend(fontsize=8, loc="upper left")
    ygrid(ax, t)


@figure("theory", size=(9.0, 3.4))
def _(fig, t):
    a1, a2 = fig.subplots(1, 2, gridspec_kw=dict(wspace=0.28))
    rows = conc()["e4_open_loop"]
    mu = rows[0]["mu"]
    S = 1000 / mu
    md = lambda p: S + p * S / (2 * (1 - p))
    mm = lambda p: S / (1 - p)
    p0 = rows[0]["rps"] / mu
    delta = rows[0]["mean"] - md(p0)
    pp = np.linspace(0.15, 0.97, 200)
    a1.plot(pp, md(pp) + delta, color=t["c"][GREEN], label="M/D/1 + δ")
    a1.plot(pp, mm(pp) + delta, color=t["c"][ORANGE], ls="--", label="M/M/1 + δ")
    a1.scatter([r["rps"] / mu for r in rows], [r["mean"] for r in rows], color=t["c"][BLUE], zorder=3, label="đo được")
    a1.set_ylim(0, 60); a1.set_xlabel("ρ"); a1.set_ylabel("latency trung bình (ms)")
    a1.set_title(f"Trung bình: S = {S:.2f} ms, δ = {delta:.1f} ms")
    a1.legend(fontsize=7.8); ygrid(a1, t)
    sim_r, sim_p99 = [], []
    for r in rows:
        p = r["rps"] / mu
        w = _mdl(S, p, n=60000, delta=delta)
        sim_r.append(p); sim_p99.append(np.percentile(w, 99))
    a2.plot(sim_r, sim_p99, color=t["c"][GREEN], marker=".", label="M/D/1 mô phỏng (Lindley)")
    a2.scatter([r["rps"] / mu for r in rows], [r["p99"] for r in rows], color=t["c"][RED], zorder=3, label="đo được")
    a2.set_xlabel("ρ"); a2.set_ylabel("p99 (ms)"); a2.set_title("p99: mô phỏng so với đo")
    a2.legend(fontsize=7.8); ygrid(a2, t)


@figure("nagle", size=(9.2, 3.4))
def _(fig, t):
    a1, a2 = fig.subplots(1, 2, gridspec_kw=dict(width_ratios=[1.2, 1], wspace=0.35))
    rows = [r for r in conc()["e3_workers"] if r["endpoint"] == "/invoices"]
    W = [1, 2, 3, 4]
    dflt = [next(r["rps"] for r in rows if r["workers"] == w and (r["nodelay"] if w == 1 else not r["nodelay"])) for w in W]
    fix = [next(r["rps"] for r in rows if r["workers"] == w and r["nodelay"]) for w in W]
    x = np.arange(4)
    a1.bar(x - 0.18, dflt, 0.34, color=t["c"][RED], label="mặc định (asyncio, --workers)")
    a1.bar(x + 0.18, fix, 0.34, color=t["c"][GREEN], label="ép TCP_NODELAY")
    for xi, v in zip(x - 0.18, dflt):
        a1.text(xi, v + 80, f"{v:.0f}", ha="center", fontsize=7.4, color=t["fg"])
    for xi, v in zip(x + 0.18, fix):
        a1.text(xi, v + 80, f"{v:.0f}", ha="center", fontsize=7.4, color=t["fg"])
    a1.set_xticks(x, [f"{w} worker" for w in W]); a1.set_ylabel("req/s (POST /invoices, 32 kết nối)")
    a1.set_title("e3: thêm worker mà chậm hơn"); a1.legend(fontsize=7.4, loc="upper left"); a1.set_ylim(0, 6500)
    ygrid(a1, t)
    e9 = conc()["e9_nagle"]
    labels = [f"{r['loop']}\n{r['workers']} worker" for r in e9]
    vals = [r["p50"] for r in e9]
    cols = [t["c"][RED] if v > 10 else t["c"][GREEN] for v in vals]
    a2.bar(range(len(e9)), vals, color=cols, width=0.6)
    for i, v in enumerate(vals):
        a2.text(i, v * 1.25, f"{v:.1f} ms", ha="center", fontsize=7.8, color=t["fg"])
    a2.set_yscale("log"); a2.set_ylim(0.05, 300)
    a2.set_xticks(range(len(e9)), labels, fontsize=7.6); a2.set_ylabel("p50 /health, 1 kết nối (ms)")
    a2.set_title("e9: chỉ asyncio + --workers dính ~44 ms")
    ygrid(a2, t)


@figure("usl", size=(7.6, 3.1))
def _(fig, t):
    from scipy.optimize import curve_fit
    ax = fig.subplots()
    rows = [r for r in conc()["e3_workers"] if r["endpoint"] == "/invoices" and r["nodelay"]]
    N = np.array([r["workers"] for r in rows]); X = np.array([r["rps"] for r in rows])
    lam = X[0]
    f = lambda n, s, k: lam * n / (1 + s * (n - 1) + k * n * (n - 1))
    (s, k), _ = curve_fit(f, N, X, p0=[0.05, 0.01], bounds=(0, 1))
    nn = np.linspace(1, 8, 200)
    ax.plot(nn, lam * nn, color=t["muted"], ls=":", label="tuyến tính lý tưởng")
    ax.plot(nn, f(nn, s, k), color=t["c"][BLUE], label=f"USL: σ = {s:.3f}, κ = {k:.3f}")
    ax.scatter(N, X, color=t["c"][ORANGE], zorder=3, s=40, label="đo được (đã ép TCP_NODELAY)")
    ns = np.sqrt((1 - s) / k)
    ax.axvline(ns, color=t["c"][RED], ls="--", lw=1)
    ax.text(ns + 0.1, 1500, f"N* ≈ {ns:.1f}", color=t["c"][RED], fontsize=8)
    ax.set_xlabel("số worker N"); ax.set_ylabel("req/s"); ax.set_ylim(0, 10000)
    ax.set_title("Universal Scalability Law khớp với e3 (client chạy chung 4 vCPU)")
    ax.legend(fontsize=7.8, loc="upper left")
    ygrid(ax, t)


@figure("capacity", size=(9.4, 3.8))
def _(fig, t):
    ax = canvas(fig, (0, 132), (0, 52))
    cb, co = t["c"][BLUE], t["c"][ORANGE]
    ax.text(2, 48, "invoice-api", fontsize=9.4, weight="bold", color=cb)
    rows = [("λ = 500 req/s, W ≈ 6 ms", "L = λW = 3 request đồng thời"), ("CPU ~0,25 ms/request", "a = 0,125 core → CPU không phải nút thắt"),
            ("DB ~5 ms/request", "≈ 2,5 kết nối bận → pool 5–10/pod (M10)"), ("3 pod × 1 tiến trình", "chịu mất 1 zone, burst cuối tháng"),
            ("--limit-concurrency 200, timeout 2 s", "từ chối sớm khi quá tải")]
    for i, (a, b) in enumerate(rows):
        y = 41 - i * 7.6
        box(ax, 2, y - 2.6, 26, 5.4, a, t, color=cb, fill=tint(cb, t, .14), fs=7.2)
        ax.text(30, y, b, fontsize=7.6, color=t["fg"], va="center")
    ax.text(70, 48, "ai-gateway", fontsize=9.4, weight="bold", color=co)
    rows = [("λ = 0,4 lượt/s, W ≈ 15 s", "L = 6 lượt đồng thời (burst ×3 → 18)"), ("mọi I/O async", "1 event loop đủ cho hàng trăm lượt chờ"),
            ("Semaphore LLM 20/tiến trình", "khớp hạn mức nhà cung cấp"), ("timeout đọc 30 s, toàn lượt 60 s", "503 + Retry-After khi hết chỗ"),
            ("60 SSE mở lâu", "~60 KB coroutine; ping mỗi 15 s")]
    for i, (a, b) in enumerate(rows):
        y = 41 - i * 7.6
        box(ax, 70, y - 2.6, 26, 5.4, a, t, color=co, fill=tint(co, t, .14), fs=7.2)
        ax.text(98, y, b, fontsize=7.6, color=t["fg"], va="center")


if __name__ == "__main__":
    run("09")
