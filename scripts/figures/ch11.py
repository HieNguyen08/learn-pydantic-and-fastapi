"""Hình minh họa cho Module 11 — Bảo mật API (số liệu: scripts/bench/results/security.json, misc.json)."""
import numpy as np
from matplotlib.patches import Rectangle

from figkit import (AQUA, BLUE, GREEN, MAGENTA, ORANGE, RED, VIOLET, YELLOW, arrow, bench, box,
                    canvas, figure, run, tint, xgrid, ygrid)


def sec():
    return bench("security")


def boundary(ax, x, y, w, h, label, t, color):
    ax.add_patch(Rectangle((x, y), w, h, fill=False, ls="--", lw=1.2, edgecolor=color))
    ax.text(x + 1, y + 1.2, label, fontsize=7.2, color=color, va="bottom")


@figure("threat", size=(9.8, 4.4))
def _(fig, t):
    ax = canvas(fig, (0, 140), (0, 62))
    cb, co, cg, cv, cr, cm = (t["c"][k] for k in (BLUE, ORANGE, GREEN, VIOLET, RED, MAGENTA))
    boundary(ax, 30, 4, 108, 50, "ranh giới: mạng của Mekong Cloud", t, cr)
    boundary(ax, 99, 8, 37, 25, "ranh giới: dữ liệu", t, cv)
    box(ax, 2, 40, 22, 9, "12.000 POS/ERP\n(tenant)", t, color=co, fill=tint(co, t, .14), fs=7.4)
    box(ax, 2, 24, 22, 9, "trình duyệt\nnhân viên CS", t, color=co, fill=tint(co, t, .14), fs=7.4)
    box(ax, 2, 8, 22, 9, "Zendesk\nwebhook", t, color=co, fill=tint(co, t, .14), fs=7.4)
    box(ax, 36, 38, 22, 9, "proxy / LB\nTLS, giới hạn body", t, color=t["line"], fs=7.2)
    box(ax, 70, 40, 24, 9, "invoice-api", t, color=cb, fill=tint(cb, t, .15), fs=7.8, weight="bold")
    box(ax, 70, 24, 24, 9, "ai-gateway", t, color=cb, fill=tint(cb, t, .15), fs=7.8, weight="bold")
    box(ax, 102, 22.5, 30, 7, "PostgreSQL (RLS)", t, color=cv, fill=tint(cv, t, .15), fs=7.4)
    box(ax, 102, 12, 30, 7, "Redis (rate limit)", t, color=cv, fill=tint(cv, t, .15), fs=7.4)
    box(ax, 106, 44, 28, 8, "LLM provider\n(bên ngoài)", t, color=cm, fill=tint(cm, t, .12), fs=7.2)
    box(ax, 36, 14, 22, 9, "URL webhook\ncủa tenant", t, color=cm, fill=tint(cm, t, .12), fs=7.2)
    for (x1, y1, x2, y2) in ((24.3, 44.5, 35.7, 43), (24.3, 28.5, 35.7, 41), (24.3, 12.5, 35.7, 40),
                             (58.3, 43, 69.7, 44.5), (58.3, 41, 69.7, 28.5), (94.3, 44, 101.7, 27),
                             (94.3, 27, 101.7, 24), (94.3, 26, 101.7, 15.5), (94.3, 30, 105.7, 47),
                             (69.7, 25, 58.3, 18.5)):
        arrow(ax, x1, y1, x2, y2, t, lw=1, color=t["fg2"])
    tags = [(31, 55.2, "S T D: token giả, body khổng lồ"), (66, 55.2, "E I: BFLA, BOLA"),
            (99, 34, "I: thiếu tenant_id → lộ dữ liệu"), (36, 10, "SSRF (API7)"),
            (106, 56, "API10: không tin output LLM")]
    for x, y, s in tags:
        ax.text(x, y, s, fontsize=7.2, color=cr)
    ax.text(2, 59.5, "Sơ đồ luồng dữ liệu và ranh giới tin cậy — mỗi mũi tên cắt qua đường đứt là một chỗ phải kiểm",
            fontsize=9, weight="bold", color=t["fg"])


@figure("owasp", size=(9.8, 4.2))
def _(fig, t):
    ax = canvas(fig, (0, 140), (0, 60))
    items = [("API1", "BOLA", "tenant_id + RLS + 404", RED),
             ("API2", "Broken Authentication", "JWT: alg cố định, aud, exp", RED),
             ("API3", "BOPLA", "model In/Out, extra=forbid", RED),
             ("API4", "Resource Consumption", "giới hạn body, độ sâu,\nmax_length, rate limit", ORANGE),
             ("API5", "BFLA", "Security(scopes=…)", RED),
             ("API6", "Sensitive Business Flows", "rate limit theo tenant/chi phí", ORANGE),
             ("API7", "SSRF", "HttpUrl + resolve +\nis_global + egress proxy", VIOLET),
             ("API8", "Misconfiguration", "CORS đúng, không lộ\nstack trace", VIOLET),
             ("API9", "Inventory Management", "OpenAPI là nguồn sự thật,\ntắt bản cũ (M13)", VIOLET),
             ("API10", "Unsafe Consumption", "validate dữ liệu ngoài\nvà output LLM (M15)", VIOLET)]
    for i, (code, name, fix, c) in enumerate(items):
        col, row = i % 5, i // 5
        x, y = 2 + col * 27.6, 30 - row * 26
        cc = t["c"][c]
        box(ax, x, y, 26, 23, "", t, color=cc, fill=tint(cc, t, .08))
        ax.text(x + 1.5, y + 20, code, fontsize=8.6, weight="bold", color=cc)
        ax.text(x + 1.5, y + 15.8, name, fontsize=7.2, color=t["fg"], weight="bold")
        ax.text(x + 1.5, y + 11, fix, fontsize=6.9, color=t["fg2"], va="top")
    ax.text(2, 57, "OWASP API Security Top 10 (2023) → cơ chế chặn trong khóa", fontsize=9.2, weight="bold", color=t["fg"])
    ax.text(84, 57, "■ phân quyền/xác thực", fontsize=7.4, color=t["c"][RED])
    ax.text(105, 57, "■ tài nguyên", fontsize=7.4, color=t["c"][ORANGE])
    ax.text(119, 57, "■ cấu hình/khác", fontsize=7.4, color=t["c"][VIOLET])


@figure("oauth", size=(9.8, 4.0))
def _(fig, t):
    ax = canvas(fig, (0, 140), (0, 56))
    cb, co, cg, cv = t["c"][BLUE], t["c"][ORANGE], t["c"][GREEN], t["c"][VIOLET]
    ax.text(2, 52, "Máy với máy: client credentials", fontsize=8.8, weight="bold", color=cb)
    box(ax, 2, 30, 16, 8, "máy POS", t, color=co, fill=tint(co, t, .14), fs=7.6)
    box(ax, 28, 40, 20, 8, "IdP\n/oauth/token", t, color=cv, fill=tint(cv, t, .14), fs=7.4)
    box(ax, 28, 20, 20, 8, "invoice-api", t, color=cb, fill=tint(cb, t, .14), fs=7.6)
    arrow(ax, 18.3, 36, 27.7, 43, t, color=cv, lw=1.1)
    ax.text(2, 46, "① client_id + secret\n(hoặc mTLS)", fontsize=6.8, color=cv)
    arrow(ax, 27.7, 42, 18.3, 35, t, color=cv, lw=1.1, ls="--")
    ax.text(30, 35, "② JWT 10 phút\n(mũi tên đứt)", fontsize=6.8, color=cv)
    arrow(ax, 18.3, 32, 27.7, 25, t, color=cb, lw=1.1)
    ax.text(5, 24, "③ Bearer JWT\n(aud=invoice-api,\nscope=invoice:write)", fontsize=6.8, color=cb, va="top")
    ax.text(28, 16, "kiểm chữ ký bằng khóa công khai\n(JWKS, cache theo kid)", fontsize=6.8, color=t["fg2"], va="top")
    ax.plot([60, 60], [4, 54], color=t["grid"], lw=1)
    ax.text(64, 52, "Người dùng: authorization code + PKCE", fontsize=8.8, weight="bold", color=cg)
    box(ax, 64, 30, 18, 8, "trình duyệt", t, color=co, fill=tint(co, t, .14), fs=7.6)
    box(ax, 92, 40, 18, 8, "IdP (OIDC)\nđăng nhập", t, color=cv, fill=tint(cv, t, .14), fs=7.4)
    box(ax, 92, 20, 18, 8, "BFF của UI\n(server)", t, color=cg, fill=tint(cg, t, .14), fs=7.4)
    box(ax, 120, 20, 18, 8, "ai-gateway", t, color=cb, fill=tint(cb, t, .14), fs=7.6)
    arrow(ax, 82.3, 36, 91.7, 43, t, color=cv, lw=1.1)
    ax.text(64, 45, "① chuyển hướng +\ncode_challenge", fontsize=6.8, color=cv)
    arrow(ax, 91.7, 41, 82.3, 34, t, color=cv, lw=1.1, ls="--")
    ax.text(94, 35, "② code (đứt)", fontsize=6.8, color=cv)
    arrow(ax, 82.3, 32, 91.7, 25, t, color=cg, lw=1.1)
    ax.text(64, 22, "③ code → BFF đổi lấy token\nbằng code_verifier", fontsize=6.8, color=cg, va="top")
    arrow(ax, 110.3, 24, 119.7, 24, t, color=cb, lw=1.1)
    ax.text(92, 15, "token ở server; trình duyệt chỉ giữ\ncookie HttpOnly; Secure; SameSite", fontsize=6.8,
            color=t["fg2"], va="top")
    ax.text(2, 4, "RFC 9700: bỏ implicit và password grant · PKCE cho mọi code flow · token giới hạn theo audience, scope, "
                  "người gửi (mTLS/DPoP)", fontsize=7.2, color=t["fg2"])


@figure("jwt", size=(9.6, 3.8))
def _(fig, t):
    ax = canvas(fig, (0, 136), (0, 52))
    cr, cv, cb = t["c"][RED], t["c"][VIOLET], t["c"][BLUE]
    parts = [(2, 30, "header", '{"alg":"EdDSA",\n "kid":"2026-10",\n "typ":"at+jwt"}', cr),
             (36, 56, "payload (claims)", '{"iss":"https://id.mekong.vn",\n "aud":"invoice-api", "sub":"pos-001",\n'
              ' "tid":7, "scope":"invoice:write",\n "iat":…, "exp":… (+10 phút)}', cv),
             (96, 38, "signature", "Ed25519(khóa bí mật IdP,\n base64url(header) + \".\" +\n base64url(payload))", cb)]
    for x, w, name, body, c in parts:
        box(ax, x, 26, w - 4, 16, "", t, color=c, fill=tint(c, t, .1))
        ax.text(x + 1.5, 39.5, name, fontsize=8, weight="bold", color=c)
        ax.text(x + 1.5, 36.5, body, fontsize=6.6, family="monospace", color=t["fg"], va="top")
    ax.text(31, 33, ".", fontsize=18, color=t["fg2"], ha="center")
    ax.text(91, 33, ".", fontsize=18, color=t["fg2"], ha="center")
    ax.text(2, 48, "JWT = base64url(header) . base64url(payload) . base64url(signature) — đọc được, KHÔNG mã hóa",
            fontsize=9, weight="bold", color=t["fg"])
    checks = ["① alg ∈ danh sách cố định của server (không đọc từ header để quyết định)",
              "② chữ ký đúng với khóa công khai theo kid (JWKS)",
              "③ exp, nbf (lệch đồng hồ ≤ 30 s) · iss = IdP mong đợi · aud = invoice-api",
              "④ claims qua model Pydantic: tid > 0, scope tách thành tập → Principal"]
    for i, s in enumerate(checks):
        ax.text(2, 21 - i * 5, s, fontsize=7.6, color=t["fg2"])


@figure("jwt-attacks", size=(9.6, 3.6))
def _(fig, t):
    rows = sec()["s2_jwt_attacks"]
    ax = canvas(fig, (0, 136), (0, 50))
    ax.text(2, 47, "Số đo thật (s2): 5 token tấn công qua hai decoder", fontsize=9, weight="bold", color=t["fg"])
    ax.text(58, 41, "decoder tự viết\n(làm theo header)", fontsize=7.6, color=t["fg2"], ha="center")
    ax.text(102, 41, "PyJWT\n(algorithms cố định, audience)", fontsize=7.6, color=t["fg2"], ha="center")
    for i, r in enumerate(rows):
        y = 30 - i * 6.6
        ax.text(2, y + 2.5, r["attack"], fontsize=7.6, color=t["fg"], va="center")
        for x, txt in ((40, r["naive"]), (82, r["pyjwt"])):
            ok = txt.startswith("CHẤP NHẬN")
            c = t["c"][RED] if ok else t["c"][GREEN]
            label = "CHẤP NHẬN — giả mạo thành công" if ok else txt.split(":")[1].strip()
            box(ax, x, y, 38, 5.2, label, t, color=c, fill=tint(c, t, .18), fs=7)


@figure("jwt-cost", size=(8.4, 3.2))
def _(fig, t):
    rows = sec()["s1_jwt_cost"]
    ax = fig.subplots()
    x = np.arange(len(rows))
    ax.bar(x - 0.2, [r["sign_us"] for r in rows], 0.4, color=t["c"][VIOLET], label="ký (IdP)")
    ax.bar(x + 0.2, [r["verify_us"] for r in rows], 0.4, color=t["c"][BLUE], label="kiểm (mỗi request ở API)")
    for i, r in enumerate(rows):
        ax.text(i + 0.2, r["verify_us"] + 6, f"{r['verify_us']:.0f}", ha="center", fontsize=7.6, color=t["fg2"])
        ax.text(i - 0.2, r["sign_us"] + 6, f"{r['sign_us']:.0f}", ha="center", fontsize=7.6, color=t["fg2"])
    ax.set_xticks(x, [f"{r['alg']}\n({r['token_bytes']} byte)" for r in rows])
    ax.set_ylabel("µs")
    ax.set_title("Số đo thật (s1): chi phí JWT theo thuật toán (PyJWT + cryptography)")
    ax.legend(fontsize=8)
    ygrid(ax, t)


@figure("hash", size=(9.8, 3.8))
def _(fig, t):
    h = bench("misc")["hash"]
    ax1, ax2 = fig.subplots(1, 2, gridspec_kw=dict(width_ratios=[1.25, 1]))
    names = [r["alg"].replace(" (KHÔNG dùng cho mật khẩu)", "").replace(" (OWASP)", " ★").replace(" (RFC 9106 low-mem)", "")
             for r in h]
    cols = [t["c"][RED]] + [t["c"][ORANGE]] + [t["c"][YELLOW]] * 2 + [t["c"][GREEN]] * 3
    ax1.barh(names, [r["ms"] for r in h], color=cols)
    ax1.set_xscale("log")
    for i, r in enumerate(h):
        ax1.text(r["ms"] * 1.15, i, f"{r['ms']:.3g} ms".replace(".", ","), va="center", fontsize=7.2, color=t["fg2"])
    ax1.set_xlim(3e-4, 4e3)
    ax1.invert_yaxis()
    ax1.tick_params(axis="y", labelsize=7)
    ax1.set_xlabel("ms mỗi lần băm (1 core, log)")
    ax1.set_title("Số đo thật: chi phí một lần băm")
    xgrid(ax1, t)
    # brute-force: 8 ký tự a-z0-9, kỳ vọng nửa không gian
    half = 36 ** 8 / 2
    year = 3.15e7
    att = [("SHA-256\n1 GPU RTX 4090", half / 2.18e10 / year, RED),
           ("bcrypt-10\n1.000 core", half / (1000 / (h[2]["ms"] / 1000)) / year, YELLOW),
           ("Argon2id 19 MiB\n1.000 core", half / (1000 / (h[4]["ms"] / 1000)) / year, GREEN)]
    ax2.bar([a[0] for a in att], [a[1] for a in att], color=[t["c"][a[2]] for a in att])
    ax2.set_yscale("log")
    labels = ["65 giây", f"{att[1][1]:.1f} năm".replace(".", ","), f"{att[2][1]:.1f} năm".replace(".", ",")]
    for i, (a, l) in enumerate(zip(att, labels)):
        ax2.text(i, a[1] * 1.6, l, ha="center", fontsize=7.6, color=t["fg"])
    ax2.set_ylim(1e-7, 50)
    ax2.set_ylabel("năm (log)")
    ax2.tick_params(axis="x", labelsize=7.2)
    ax2.set_title("Ước lượng: phá mật khẩu 8 ký tự a-z0-9")
    ygrid(ax2, t)
    fig.tight_layout()


@figure("bola", size=(9.6, 3.8))
def _(fig, t):
    ax = canvas(fig, (0, 136), (0, 52))
    cr, cg, cb, co = t["c"][RED], t["c"][GREEN], t["c"][BLUE], t["c"][ORANGE]
    box(ax, 2, 22, 24, 10, "POS tenant 7\nGET /v1/invoices/102", t, color=co, fill=tint(co, t, .14), fs=7.4)
    box(ax, 34, 22, 24, 10, "current_principal\n→ tid = 7 (từ JWT)", t, color=cb, fill=tint(cb, t, .14), fs=7.2)
    arrow(ax, 26.3, 27, 33.7, 27, t)
    ax.text(62, 47, "Thiếu kiểm theo đối tượng", fontsize=8.4, weight="bold", color=cr)
    box(ax, 62, 33, 34, 9, "SELECT … WHERE id = 102", t, color=cr, fill=tint(cr, t, .12), fs=7.2)
    box(ax, 104, 33, 30, 9, "200 + hóa đơn của\ntenant 9 (LỘ)", t, color=cr, fill=tint(cr, t, .2), fs=7.2)
    arrow(ax, 58.3, 30, 61.7, 37, t, color=cr)
    arrow(ax, 96.3, 37.5, 103.7, 37.5, t, color=cr)
    ax.text(62, 24, "Đúng: tenant từ principal, không từ request", fontsize=8.4, weight="bold", color=cg)
    box(ax, 62, 10, 34, 9, "SELECT … WHERE id = 102\nAND tenant_id = 7  (+ RLS)", t, color=cg, fill=tint(cg, t, .12), fs=7)
    box(ax, 104, 10, 30, 9, "0 hàng → 404\n(như không tồn tại)", t, color=cg, fill=tint(cg, t, .2), fs=7.2)
    arrow(ax, 58.3, 25, 61.7, 15, t, color=cg)
    arrow(ax, 96.3, 14.5, 103.7, 14.5, t, color=cg)
    ax.text(2, 49, "BOLA (API1): token hợp lệ không có nghĩa là được xem MỌI đối tượng", fontsize=9, weight="bold",
            color=t["fg"])
    ax.text(2, 4, "403 sẽ xác nhận hóa đơn 102 tồn tại → dò được số lượng hóa đơn của đối thủ", fontsize=7.4,
            color=t["fg2"])


@figure("bopla", size=(9.6, 3.6))
def _(fig, t):
    d = sec()["s7_mass_assignment"]
    ax = canvas(fig, (0, 136), (0, 52))
    cr, cy, cg = t["c"][RED], t["c"][YELLOW], t["c"][GREEN]
    body = '{"buyer_name": "Cty A (sửa)",\n "status": "signed",\n "tenant_id": 1,\n "total": 0}'
    box(ax, 2, 14, 32, 22, "", t, color=t["line"])
    ax.text(3.5, 33, "PATCH /v1/invoices/101", fontsize=7.4, weight="bold", color=t["fg"])
    ax.text(3.5, 29, body, fontsize=6.8, family="monospace", color=t["fg"], va="top")
    nv = d["naive_result"]
    ig = d["ignore_result"]
    outs = [(33, "setattr(inv, k, v) cho mọi khóa",
             f"tenant_id={nv['tenant_id']}  status={nv['status']}  total={nv['total']}\n→ chuyển tenant, bỏ qua quy trình ký",
             cr),
            (20, "InvoicePatch (extra mặc định = ignore)",
             f"tenant_id={ig['tenant_id']}  status={ig['status']}  total={ig['total']}\n→ an toàn, nhưng lặng lẽ bỏ qua",
             cy),
            (7, "InvoicePatch (extra=\"forbid\")",
             "422: " + ", ".join(f"{loc} {typ}" for loc, typ in d["forbid_errors"]).replace("extra_forbidden", "extra_forbidden")
             + "\n→ an toàn và báo lỗi rõ ràng", cg)]
    outs = [(y + 1, h, txt, c) for y, h, txt, c in outs]
    for y, h, txt, c in outs:
        arrow(ax, 34.3, 25, 43.7, y + 5, t, color=c, lw=1.1)
        box(ax, 44, y, 90, 11, "", t, color=c, fill=tint(c, t, .1))
        ax.text(46, y + 8.2, h, fontsize=7.6, weight="bold", color=c)
        ax.text(46, y + 5.4, txt, fontsize=6.8, color=t["fg"], va="top")
    ax.text(2, 49, "Số đo thật (s7): mass assignment — BOPLA (API3)", fontsize=9, weight="bold", color=t["fg"])


@figure("ratelimit", size=(9.8, 3.6))
def _(fig, t):
    sim = sec()["s3_rate_limit"]["sim"]
    ax1, ax2 = fig.subplots(1, 2, gridspec_kw=dict(width_ratios=[1, 1.5]))
    for ax, lo, hi in ((ax1, 0.94, 1.045), (ax2, -0.05, 4.0)):
        for k, y in (("fixed", 1.0), ("gcra", 0.0)):
            ok = [r["t"] for r in sim if r[k] and lo <= r["t"] <= hi]
            no = [r["t"] for r in sim if not r[k] and lo <= r["t"] <= hi]
            ax.scatter(ok, [y] * len(ok), marker="|", s=260, color=t["c"][GREEN], lw=1.6)
            ax.scatter(no, [y] * len(no), marker="x", s=30, color=t["c"][RED], lw=1.2)
        ax.set_xlim(lo, hi)
        ax.set_ylim(-0.6, 1.6)
        ax.set_yticks([0, 1], ["GCRA\nr=10/s, b=10", "cửa sổ cố định\n10/s"], fontsize=7.6)
        for sp in ("right", "top"):
            ax.spines[sp].set_visible(False)
    for sx in (1.0, 2.0, 3.0):
        ax2.axvline(sx, color=t["fg2"], ls=":", lw=1)
    ax1.axvline(1.0, color=t["fg2"], ls=":", lw=1)
    ax2.axvspan(0.94, 1.045, color=t["c"][ORANGE], alpha=0.12)
    n_fw = sum(r["fixed"] for r in sim if 0.9 <= r["t"] < 1.1)
    n_g = sum(r["gcra"] for r in sim if 0.9 <= r["t"] < 1.1)
    ax1.set_title(f"Phóng to quanh mốc 1 s: cố định nhận {n_fw}, GCRA nhận {n_g}", fontsize=8.6)
    ax1.set_xlabel("thời gian (s)")
    ax2.set_title("Toàn bộ: sau đó gửi đều 10/s → cả hai đều nhận", fontsize=8.6)
    ax2.set_xlabel("thời gian (s) — đường chấm: ranh giới cửa sổ")
    ax2.scatter([], [], marker="|", s=80, color=t["c"][GREEN], label="nhận")
    ax2.scatter([], [], marker="x", s=30, color=t["c"][RED], label="429")
    ax2.legend(fontsize=8, loc="center right")
    fig.suptitle("Mô phỏng (s3): dồn 20 request quanh ranh giới giây", fontsize=9.4, color=t["fg"])
    fig.tight_layout()


@figure("payload", size=(9.8, 3.6))
def _(fig, t):
    d = sec()["s4_payload"]
    ax1, ax2 = fig.subplots(1, 2, gridspec_kw=dict(width_ratios=[1.2, 1]))
    rows = d["big_list"]
    ax1.plot([r["mb"] for r in rows], [r["ms"] for r in rows], marker="o", color=t["c"][RED])
    for r in rows:
        if r["lines"] >= 50_000:
            ax1.text(r["mb"] - 0.2, r["ms"] + 8, f"{r['lines']:,} dòng".replace(",", "."), fontsize=7.2,
                     color=t["fg2"], ha="right")
    ax1.set_xlabel("kích thước body (MB)")
    ax1.set_ylabel("ms để model_validate_json trả lỗi")
    ax1.set_title("max_length=500 vẫn phải đọc hết input")
    ygrid(ax1, t)
    fb = d["fastapi_body"]
    labels = ["không giới hạn\n(422)", "RequestBodyLimit\n1 MiB (413)"]
    x = np.arange(2)
    ax2.bar(x - 0.2, [r["ms"] for r in fb], 0.4, color=t["c"][ORANGE], label="thời gian (ms)")
    ax2.bar(x + 0.2, [max(r["peak_mib"], 0.01) for r in fb], 0.4, color=t["c"][VIOLET], label="đỉnh bộ nhớ (MiB)")
    ax2.set_yscale("log")
    for i, r in enumerate(fb):
        ms = f"{r['ms']:.0f}".replace(",", ".") if r["ms"] >= 100 else f"{r['ms']:.2g}".replace(".", ",")
        ax2.text(i - 0.2, r["ms"] * 1.3, f"{int(r['ms']):,}".replace(",", ".") if r["ms"] >= 100 else ms,
                 ha="center", fontsize=7.4, color=t["fg"])
        pk = r["peak_mib"]
        ax2.text(i + 0.2, max(pk, 0.01) * 1.3, f"{pk:.0f}" if pk >= 10 else f"{pk:.2g}".replace(".", ","), ha="center",
                 fontsize=7.4, color=t["fg"])
    ax2.set_xticks(x, labels, fontsize=7.6)
    ax2.set_ylim(0.005, 3e4)
    ax2.set_title(f"Body {fb[0]['body_mb']:.0f} MB qua FastAPI")
    ax2.legend(fontsize=7.4, loc="upper right")
    ygrid(ax2, t)
    fig.suptitle("Số đo thật (s4): DoS qua payload", fontsize=9.4, color=t["fg"])
    fig.tight_layout()


@figure("ssrf", size=(9.8, 3.8))
def _(fig, t):
    ax = canvas(fig, (0, 140), (0, 54))
    cb, cg, cr, cv, co = (t["c"][k] for k in (BLUE, GREEN, RED, VIOLET, ORANGE))
    steps = [("URL tenant nhập", "http://0x7f000001/\nhttp://127.0.0.1#@evil.com/", co),
             ("Pydantic HttpUrl", "chuẩn hóa WHATWG\nhost = 127.0.0.1\nscheme ∈ {http, https}", cb),
             ("phân giải DNS", "getaddrinfo(host)\n→ MỌI địa chỉ", cv),
             ("is_global?", "loại loopback, private,\nlink-local (169.254…),\nIPv4-mapped IPv6", cg),
             ("kết nối", "tới ĐÚNG IP đã kiểm\n(chống DNS rebinding)\nhoặc qua egress proxy", cg)]
    for i, (h, s, c) in enumerate(steps):
        x = 2 + i * 27.6
        box(ax, x, 20, 25, 20, "", t, color=c, fill=tint(c, t, .1))
        ax.text(x + 12.5, 37, h, fontsize=8, weight="bold", color=c, ha="center")
        ax.text(x + 12.5, 31.5, s, fontsize=6.7, color=t["fg"], ha="center", va="top")
        if i < len(steps) - 1:
            arrow(ax, x + 25.3, 30, x + 27.3, 30, t, lw=1)
    rows = sec()["s5_ssrf"]
    blocked = sum(not r["allowed"] for r in rows)
    ax.text(2, 13, f"Số đo thật (s5): {len(rows)} URL thử, {blocked} bị chặn — mọi cách viết trỏ về 127.0.0.1 "
                   "(hex, thập phân, bát phân, rút gọn, userinfo, fragment) đều được HttpUrl chuẩn hóa", fontsize=7.6,
            color=t["fg2"])
    ax.text(2, 7, "Sai: lọc bằng regex/chuỗi trên URL thô → parser differential (bộ lọc thấy evil.com, HTTP client "
                  "kết nối 127.0.0.1)", fontsize=7.6, color=cr)
    ax.text(2, 50, "Chặn SSRF cho URL webhook (API7)", fontsize=9.2, weight="bold", color=t["fg"])


if __name__ == "__main__":
    run("11")
