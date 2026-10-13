"""Thí nghiệm bảo mật cho Module 11 → results/security.json

  s1  chi phí ký/kiểm JWT theo thuật toán (HS256, RS256, ES256, EdDSA)
  s2  tấn công JWT: alg=none, nhầm thuật toán (RS256 → HS256), thiếu aud/exp — decoder ngây thơ vs PyJWT
  s3  rate limit: cửa sổ cố định vs GCRA (mô phỏng), và GCRA trên Redis thật với client đồng thời
  s4  DoS qua payload: độ sâu JSON, danh sách cực lớn, body 20 MB qua FastAPI có/không giới hạn
  s5  SSRF: Pydantic HttpUrl chuẩn hóa các cách viết IP lạ; bộ lọc địa chỉ nội bộ
  s6  CORS: CORSMiddleware với allow_origins=["*"] + allow_credentials
  s7  mass assignment: setattr từ dict vs model Pydantic extra="forbid"
  s8  băm mật khẩu trong threadpool: argon2-cffi/bcrypt nhả GIL
Chạy:  python bench_security.py [--only s1 s3]   (s3 cần redis-server, REDIS_URL mặc định redis://localhost:6390)
"""
import argparse
import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import os
import socket
import time
import tracemalloc
from pathlib import Path
from typing import Annotated

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa

HERE = Path(__file__).parent
OUT = HERE / "results" / "security.json"


def bench_us(fn, n):
    best = float("inf")
    for _ in range(5):
        t0 = time.perf_counter()
        for _ in range(n):
            fn()
        best = min(best, (time.perf_counter() - t0) / n * 1e6)
    return best


# ---------------------------------------------------------------- s1
def s1_jwt_cost(res):
    claims = {"sub": "user-42", "tid": 7, "scope": "invoice:write", "aud": "invoice-api", "iss": "https://id.mekong.vn",
              "exp": int(time.time()) + 600}
    keys = {
        "HS256": (b"k" * 32, b"k" * 32),
        "RS256": (lambda k: (k, k.public_key()))(rsa.generate_private_key(public_exponent=65537, key_size=2048)),
        "ES256": (lambda k: (k, k.public_key()))(ec.generate_private_key(ec.SECP256R1())),
        "EdDSA": (lambda k: (k, k.public_key()))(ed25519.Ed25519PrivateKey.generate()),
    }
    rows = []
    for alg, (priv, pub) in keys.items():
        tok = jwt.encode(claims, priv, algorithm=alg)
        n = 2000 if alg != "RS256" else 300
        sign = bench_us(lambda: jwt.encode(claims, priv, algorithm=alg), n)
        verify = bench_us(lambda: jwt.decode(tok, pub, algorithms=[alg], audience="invoice-api",
                                             issuer="https://id.mekong.vn"), 2000)
        rows.append(dict(alg=alg, sign_us=sign, verify_us=verify, token_bytes=len(tok)))
        print(f"s1 {alg:6s} ký {sign:8.1f} µs  kiểm {verify:7.1f} µs  token {len(tok)} byte")
    res["s1_jwt_cost"] = rows


# ---------------------------------------------------------------- s2
def b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def naive_decode(token: str, key):
    """Decoder 'tự viết' điển hình: tin trường alg trong header."""
    h, p, s = token.split(".")
    header = json.loads(base64.urlsafe_b64decode(h + "=="))
    if header["alg"] == "none":
        return json.loads(base64.urlsafe_b64decode(p + "=="))
    if header["alg"] == "HS256":
        k = key if isinstance(key, bytes) else key.encode()
        sig = hmac.new(k, f"{h}.{p}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(b64url(sig), s):
            raise ValueError("chữ ký sai")
        return json.loads(base64.urlsafe_b64decode(p + "=="))
    if header["alg"] == "RS256":
        return jwt.decode(token, key, algorithms=["RS256"], options={"verify_aud": False})
    raise ValueError("alg lạ")


def s2_jwt_attacks(res):
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_pem = priv.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    forged_claims = {"sub": "attacker", "tid": 1, "scope": "admin", "exp": int(time.time()) + 600, "aud": "invoice-api"}
    none_tok = f"{b64url(json.dumps({'alg': 'none', 'typ': 'JWT'}).encode())}.{b64url(json.dumps(forged_claims).encode())}."
    h = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    p = b64url(json.dumps(forged_claims).encode())
    sig = b64url(hmac.new(pub_pem, f"{h}.{p}".encode(), hashlib.sha256).digest())
    confusion_tok = f"{h}.{p}.{sig}"                          # ký HMAC bằng chính khóa CÔNG KHAI
    other_aud = jwt.encode({"sub": "u", "aud": "ai-gateway", "exp": int(time.time()) + 600}, priv, algorithm="RS256")
    expired = jwt.encode({"sub": "u", "aud": "invoice-api", "exp": int(time.time()) - 3600}, priv, algorithm="RS256")

    def try_(f):
        try:
            out = f()
            return "CHẤP NHẬN: " + json.dumps(out, ensure_ascii=False)[:60]
        except Exception as e:  # noqa: BLE001
            return f"từ chối: {type(e).__name__}: {str(e)[:90]}"

    cases = [
        ("alg=none", lambda: naive_decode(none_tok, pub_pem),
         lambda: jwt.decode(none_tok, pub_pem, algorithms=["RS256"], audience="invoice-api")),
        ("nhầm thuật toán RS256→HS256", lambda: naive_decode(confusion_tok, pub_pem),
         lambda: jwt.decode(confusion_tok, pub_pem, algorithms=["RS256"], audience="invoice-api")),
        ("nhầm thuật toán, cho phép cả HS256", lambda: naive_decode(confusion_tok, pub_pem),
         lambda: jwt.decode(confusion_tok, pub_pem, algorithms=["RS256", "HS256"], audience="invoice-api")),
        ("token của dịch vụ khác (aud)", lambda: naive_decode(other_aud, priv.public_key()),
         lambda: jwt.decode(other_aud, priv.public_key(), algorithms=["RS256"], audience="invoice-api")),
        ("token hết hạn", lambda: jwt.decode(expired, priv.public_key(), algorithms=["RS256"],
                                              options={"verify_exp": False, "verify_aud": False}),
         lambda: jwt.decode(expired, priv.public_key(), algorithms=["RS256"], audience="invoice-api")),
    ]
    rows = []
    for name, naive, good in cases:
        r = dict(attack=name, naive=try_(naive), pyjwt=try_(good))
        rows.append(r)
        print(f"s2 {name:36s}\n     ngây thơ: {r['naive']}\n     PyJWT   : {r['pyjwt']}")
    res["s2_jwt_attacks"] = rows


# ---------------------------------------------------------------- s3
class FixedWindow:
    def __init__(self, limit, window):
        self.limit, self.window, self.cur, self.count = limit, window, None, 0

    def allow(self, t):
        w = int(t // self.window)
        if w != self.cur:
            self.cur, self.count = w, 0
        if self.count < self.limit:
            self.count += 1
            return True
        return False


class GCRA:
    """Generic Cell Rate Algorithm: tương đương token bucket, chỉ lưu MỘT số (TAT)."""

    def __init__(self, rate, burst):
        self.T = 1.0 / rate                   # khoảng cách lý tưởng giữa hai request
        self.tau = (burst - 1) * self.T       # dung sai = độ lớn burst cho phép
        self.tat = 0.0                        # theoretical arrival time

    def allow(self, t):
        tat = max(self.tat, t)
        if tat - t > self.tau:
            return False
        self.tat = tat + self.T
        return True


def s3_rate_limit(res):
    # Kịch bản: giới hạn 10 req/s. Client dồn 10 request ở cuối giây 0 và 10 request ở đầu giây 1.
    arrivals = [0.95 + i * 0.004 for i in range(10)] + [1.0 + i * 0.004 for i in range(10)]
    arrivals += [2.0 + i * 0.1 for i in range(20)]           # rồi gửi đều 10 req/s trong 2 giây
    fw, g = FixedWindow(10, 1.0), GCRA(rate=10, burst=10)
    sim = [dict(t=t, fixed=fw.allow(t), gcra=g.allow(t)) for t in arrivals]
    w = [r for r in sim if 0.9 <= r["t"] < 1.1]
    print(f"s3 trong 0,2 s quanh mốc 1 s: cửa sổ cố định cho qua {sum(r['fixed'] for r in w)}, GCRA cho qua {sum(r['gcra'] for r in w)}")
    out = dict(sim=sim)
    # GCRA trên Redis thật (script Lua nguyên tử), 50 client đồng thời, 3 giây
    try:
        import redis.asyncio as aredis
        r = aredis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6390"))
        lua = """
        local key, T, tau = KEYS[1], tonumber(ARGV[1]), tonumber(ARGV[2])
        local t = redis.call('TIME'); local now = tonumber(t[1]) + tonumber(t[2]) / 1e6
        local tat = tonumber(redis.call('GET', key) or now)
        if tat < now then tat = now end
        if tat - now > tau then return 0 end
        redis.call('SET', key, tat + T, 'PX', math.ceil((tat + T - now) * 1000) + 1000)
        return 1
        """

        async def run():
            script = r.register_script(lua)
            await r.delete("rl:tenant:7")
            rate, burst, dur = 100, 20, 3.0
            T, tau = 1 / rate, (burst - 1) / rate
            allowed, total, lat = 0, 0, []
            stop = time.perf_counter() + dur

            async def client():
                nonlocal allowed, total
                while time.perf_counter() < stop:
                    t0 = time.perf_counter()
                    ok = await script(keys=["rl:tenant:7"], args=[T, tau])
                    lat.append((time.perf_counter() - t0) * 1e6)
                    total += 1
                    allowed += int(ok)
            t0 = time.perf_counter()
            await asyncio.gather(*(client() for _ in range(50)))
            dt = time.perf_counter() - t0
            # độ trễ một lần kiểm tra khi không tranh chấp (1 client tuần tự)
            await r.delete("rl:tenant:8")
            for _ in range(2000):
                t1 = time.perf_counter()
                await script(keys=["rl:tenant:8"], args=[T, tau])
                lat.append((time.perf_counter() - t1) * 1e6)
            lat = lat[-2000:]
            lat.sort()
            return dict(rate=rate, burst=burst, seconds=dt, attempts=total, allowed=allowed,
                        allowed_per_s=allowed / dt, expected_max=burst + rate * dt, checks_per_s=total / dt,
                        p50_us=lat[len(lat) // 2], p99_us=lat[int(len(lat) * .99)])
        out["redis"] = asyncio.run(run())
        x = out["redis"]
        print(f"s3 Redis GCRA: {x['attempts']} lần thử ({x['checks_per_s']:.0f}/s), cho qua {x['allowed']} "
              f"(trần lý thuyết {x['expected_max']:.0f}), {x['allowed_per_s']:.1f}/s; 1 lần kiểm tra không tranh chấp: "
              f"p50 {x['p50_us']:.0f} µs p99 {x['p99_us']:.0f} µs")
    except Exception as e:  # noqa: BLE001
        print("s3 bỏ qua Redis:", e)
    res["s3_rate_limit"] = out


# ---------------------------------------------------------------- s4
def s4_payload(res):
    from fastapi import FastAPI
    from pydantic import BaseModel, Field, TypeAdapter, ValidationError
    from starlette.middleware.body_limit import RequestBodyLimitMiddleware
    out = {}
    # (a) độ sâu
    depth_rows = []
    for depth in (100, 199, 200, 201, 1000, 100_000):
        s = "[" * depth + "]" * depth
        try:
            TypeAdapter(object).validate_json(s)
            pyd = "ok"
        except ValidationError as e:
            pyd = e.errors()[0]["msg"]
        try:
            json.loads(s)
            std = "ok"
        except RecursionError:
            std = "RecursionError"
        depth_rows.append(dict(depth=depth, pydantic=pyd, json_loads=std))
        print(f"s4 độ sâu {depth:6d}: model_validate_json → {pyd}; json.loads → {std}")
    out["depth"] = depth_rows

    # (b) danh sách lớn với max_length=500: chi phí từ chối tăng theo kích thước input
    class Line(BaseModel):
        name: str
        amount: int

    class Inv(BaseModel):
        lines: Annotated[list[Line], Field(max_length=500)]

    big_rows = []
    for n in (500, 5_000, 50_000, 200_000):
        body = json.dumps({"lines": [{"name": "Cà phê", "amount": 30000}] * n}).encode()
        best = float("inf")
        for _ in range(3):
            t0 = time.perf_counter()
            try:
                Inv.model_validate_json(body)
            except ValidationError:
                pass
            best = min(best, (time.perf_counter() - t0) * 1000)
        big_rows.append(dict(lines=n, mb=len(body) / 1e6, ms=best))
        print(f"s4 {n:7d} dòng ({len(body) / 1e6:5.2f} MB): {best:7.1f} ms để {'nhận' if n <= 500 else 'từ chối'}")
    out["big_list"] = big_rows

    # (c) body 20 MB qua FastAPI, có và không có RequestBodyLimitMiddleware
    def make(limit):
        app = FastAPI()

        @app.post("/v1/invoices")
        async def create(inv: Inv):
            return {"n": len(inv.lines)}
        return RequestBodyLimitMiddleware(app, max_body_size=limit) if limit else app

    body = json.dumps({"lines": [{"name": "Cà phê", "amount": 30000}] * 500_000}).encode()

    async def call(app):
        chunks = [body[i:i + 65536] for i in range(0, len(body), 65536)]
        sent = {"status": None}
        idx = 0

        async def receive():
            nonlocal idx
            if idx < len(chunks):
                idx += 1
                return {"type": "http.request", "body": chunks[idx - 1], "more_body": idx < len(chunks)}
            return {"type": "http.disconnect"}

        async def send(m):
            if m["type"] == "http.response.start":
                sent["status"] = m["status"]
        scope = {"type": "http", "method": "POST", "path": "/v1/invoices", "headers": [
            (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            "query_string": b"", "http_version": "1.1", "scheme": "http", "server": ("t", 80), "client": ("c", 1),
            "root_path": ""}
        t0 = time.perf_counter()
        await app(scope, receive, send)               # lần 1: đo thời gian (tracemalloc làm chậm nhiều lần)
        dt = (time.perf_counter() - t0) * 1000
        status, chunks_read = sent["status"], idx
        idx = 0
        tracemalloc.start()                           # lần 2: đo đỉnh bộ nhớ do Python cấp phát
        await app(scope, receive, send)
        peak = tracemalloc.get_traced_memory()[1] / 2**20
        tracemalloc.stop()
        return dict(status=status, ms=dt, peak_mib=peak, chunks_read=chunks_read)

    rows = []
    for label, limit in (("không giới hạn", None), ("RequestBodyLimitMiddleware 1 MiB", 1 << 20)):
        r = asyncio.run(call(make(limit)))
        r.update(case=label, body_mb=len(body) / 1e6)
        rows.append(r)
        print(f"s4 body {len(body) / 1e6:.0f} MB, {label:34s}: {r['status']} sau {r['ms']:7.1f} ms, "
              f"đỉnh bộ nhớ Python {r['peak_mib']:6.1f} MiB, đọc {r['chunks_read']} chunk")
    out["fastapi_body"] = rows
    res["s4_payload"] = out


# ---------------------------------------------------------------- s5
def is_public_host(host: str) -> tuple[bool, str]:
    """Phân giải tên miền và kiểm tra MỌI địa chỉ trả về."""
    try:
        infos = socket.getaddrinfo(host.strip("[]"), None)
    except socket.gaierror:
        return False, "không phân giải được"
    for *_, sa in infos:
        ip = ipaddress.ip_address(sa[0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global:
            return False, f"{ip} không phải địa chỉ công khai"
    return True, "công khai"


def s5_ssrf(res):
    from pydantic import HttpUrl, TypeAdapter, ValidationError
    ta = TypeAdapter(HttpUrl)
    urls = ["https://1.1.1.1/hook", "http://127.0.0.1/admin", "http://0x7f000001/", "http://2130706433/",
            "http://0177.0.0.1/", "http://127.1/", "http://[::ffff:127.0.0.1]/", "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.5:6379/", "http://localhost./", "http://evil.com@127.0.0.1/", "http://127.0.0.1#@evil.com/",
            "file:///etc/passwd", "gopher://127.0.0.1:6379/_FLUSHALL"]
    rows = []
    for u in urls:
        try:
            parsed = ta.validate_python(u)
            host = parsed.host
            ok, why = is_public_host(host)
            rows.append(dict(url=u, host=host, allowed=ok, reason=why))
        except ValidationError as e:
            rows.append(dict(url=u, host=None, allowed=False, reason="HttpUrl từ chối: " + e.errors()[0]["type"]))
        r = rows[-1]
        print(f"s5 {u:42s} host={r['host']!s:22s} {'CHO PHÉP' if r['allowed'] else 'chặn'}: {r['reason']}")
    res["s5_ssrf"] = rows


# ---------------------------------------------------------------- s6
def s6_cors(res):
    import httpx
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    rows = []
    for label, kw in (("allow_origins=['*']", dict(allow_origins=["*"])),
                      ("allow_origins=['*'], allow_credentials=True", dict(allow_origins=["*"], allow_credentials=True)),
                      ("allow_origins=['https://app.mekong.vn'], allow_credentials=True",
                       dict(allow_origins=["https://app.mekong.vn"], allow_credentials=True))):
        app = FastAPI()
        app.add_middleware(CORSMiddleware, allow_methods=["*"], allow_headers=["*"], **kw)

        @app.get("/v1/me")
        async def me():
            return {"tenant": 7}

        async def go():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
                r = await c.get("/v1/me", headers={"origin": "https://evil.example", "cookie": "session=abc"})
                return r.headers.get("access-control-allow-origin"), r.headers.get("access-control-allow-credentials")
        acao, acac = asyncio.run(go())
        rows.append(dict(config=label, origin="https://evil.example", acao=acao, acac=acac))
        print(f"s6 {label:62s} → ACAO={acao!s:22s} ACAC={acac}")
    res["s6_cors"] = rows


# ---------------------------------------------------------------- s7
def s7_mass_assignment(res):
    from pydantic import BaseModel, ConfigDict, ValidationError

    class InvoiceRow:                                   # giả lập đối tượng ORM
        def __init__(self):
            self.id, self.tenant_id, self.buyer_name, self.status, self.total = 101, 7, "Cty A", "draft", 55000

    attack = {"buyer_name": "Cty A (sửa)", "status": "signed", "tenant_id": 1, "total": 0}

    inv = InvoiceRow()
    for k, v in attack.items():                         # PATCH ngây thơ
        setattr(inv, k, v)
    naive = vars(inv).copy()

    class InvoicePatch(BaseModel):
        model_config = ConfigDict(extra="forbid")
        buyer_name: str | None = None

    try:
        InvoicePatch.model_validate(attack)
        strict = "chấp nhận"
    except ValidationError as e:
        strict = [(".".join(map(str, x["loc"])), x["type"]) for x in e.errors()]

    class InvoicePatchIgnore(BaseModel):
        buyer_name: str | None = None                   # extra mặc định "ignore"

    inv2 = InvoiceRow()
    for k, v in InvoicePatchIgnore.model_validate(attack).model_dump(exclude_unset=True).items():
        setattr(inv2, k, v)
    res["s7_mass_assignment"] = dict(attack=attack, naive_result=naive, forbid_errors=strict, ignore_result=vars(inv2))
    print("s7 ngây thơ:", naive)
    print("s7 extra=forbid:", strict)
    print("s7 extra=ignore:", vars(inv2))


# ---------------------------------------------------------------- s8
def s8_hash_threads(res):
    """argon2-cffi và bcrypt nhả GIL khi băm → chạy trong threadpool tận dụng được nhiều core."""
    from concurrent.futures import ThreadPoolExecutor

    import bcrypt
    from argon2 import PasswordHasher
    ph = PasswordHasher(time_cost=2, memory_cost=19 * 1024, parallelism=1)    # tham số OWASP
    salt = bcrypt.gensalt(10)
    fns = {"Argon2id m=19MiB t=2": lambda _: ph.hash("correct horse battery staple"),
           "bcrypt cost=10": lambda _: bcrypt.hashpw(b"correct horse battery staple", salt)}
    rows = []
    for name, f in fns.items():
        for th in (1, 2, 4):
            with ThreadPoolExecutor(th) as ex:
                t0 = time.perf_counter()
                list(ex.map(f, range(24)))
                dt = time.perf_counter() - t0
            rows.append(dict(alg=name, threads=th, per_s=24 / dt))
            print(f"s8 {name:22s} {th} luồng: {24 / dt:6.1f} lần băm/s")
    res["s8_hash_threads"] = rows


EXPS = dict(s1=s1_jwt_cost, s2=s2_jwt_attacks, s3=s3_rate_limit, s4=s4_payload, s5=s5_ssrf, s6=s6_cors,
            s7=s7_mass_assignment, s8=s8_hash_threads)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    res = json.loads(OUT.read_text()) if OUT.exists() else {}
    for k, f in EXPS.items():
        if a.only and k not in a.only:
            continue
        f(res)
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
