"""Chạy toàn bộ thí nghiệm đồng thời cho Module 08–09, ghi results/concurrency.json.

Mỗi thí nghiệm khởi động một tiến trình uvicorn riêng; bộ sinh tải chạy ở tiến trình khác
(loadgen.py) để không tranh event loop với server. Máy đo: 4 vCPU — client và server dùng
chung CPU, nên các con số tuyệt đối thấp hơn máy thật nhưng hình dạng đường cong giữ nguyên.

Chạy:  python bench_concurrency.py [--only e1 e4]
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
PY = sys.executable
PORT = 8100
BASE = f"http://127.0.0.1:{PORT}"
BODY = HERE / "results" / "invoice12.json"


def start_server(workers=1, env_extra=None, http="h11", loop="asyncio"):
    """Mặc định cố định h11 + asyncio thuần (cài `uvicorn` không kèm [standard]) để kết quả lặp lại được."""
    env = dict(os.environ, **(env_extra or {}))
    cmd = [PY, "-m", "uvicorn", "bench_app:app", "--port", str(PORT), "--log-level", "warning",
           "--no-access-log", "--workers", str(workers), "--http", http, "--loop", loop]
    p = subprocess.Popen(cmd, cwd=HERE, env=env)
    for _ in range(100):
        try:
            urllib.request.urlopen(BASE + "/health", timeout=0.5).read()
            time.sleep(0.5)
            return p
        except Exception:
            time.sleep(0.2)
    p.kill()
    raise RuntimeError("server không lên")


def stop(p):
    p.terminate()
    try:
        p.wait(10)
    except subprocess.TimeoutExpired:
        p.kill()


def load(mode, path, c=None, r=None, d=4, body=False):
    cmd = [PY, str(HERE / "loadgen.py"), mode, BASE + path, "-d", str(d)]
    if c:
        cmd += ["-c", str(c)]
    if r:
        cmd += ["-r", str(r)]
    if body:
        cmd += ["--body", str(BODY)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"loadgen lỗi: {r.stderr[-2000:]}")
    return json.loads(r.stdout.strip().splitlines()[-1])


def load_async(mode, path, c=None, d=4):
    cmd = [PY, str(HERE / "loadgen.py"), mode, BASE + path, "-d", str(d), "-c", str(c)]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)


def log(tag, r):
    print(f"{tag:38s} rps={r['rps']:8.1f} p50={r['p50']:8.1f} p99={r['p99']:9.1f} ms n={r['n']}", flush=True)


def e1_io_modes(res):
    """def vs async def vs async-chặn, I/O 50 ms, tăng dần số kết nối đồng thời."""
    p = start_server()
    out = []
    try:
        for mode in ("async", "sync", "blocking"):
            for c in (1, 2, 5, 10, 20, 40, 80, 160, 320):
                if mode == "blocking" and c > 40:
                    continue
                r = load("closed", f"/io/{mode}", c=c, d=4)
                r.update(endpoint=mode)
                out.append(r)
                log(f"e1 {mode} c={c}", r)
    finally:
        stop(p)
    res["e1_io_modes"] = out


def e2_head_of_line(res):
    """/health bị ảnh hưởng thế nào khi có tải nền vào endpoint chặn loop vs không chặn."""
    out = []
    for bg in ("none", "async", "blocking"):
        p = start_server()
        try:
            bgp = None
            if bg != "none":
                bgp = load_async("closed", f"/io/{bg}", c=20, d=8)
                time.sleep(1.5)
            r = load("closed", "/health", c=1, d=4)
            if bgp:
                bgp.wait()
            r.update(background=bg)
            out.append(r)
            log(f"e2 /health bg={bg}", r)
        finally:
            stop(p)
    res["e2_head_of_line"] = out


def e3_workers(res):
    """POST /invoices (12 dòng, validate full) theo số worker uvicorn.

    nodelay=False: hành vi mặc định của uvicorn --workers với vòng lặp asyncio (socket proto=0 →
    asyncio không bật TCP_NODELAY → Nagle + delayed ACK ~40 ms). nodelay=True: ép bật TCP_NODELAY.
    Với workers=1 uvicorn tự tạo socket qua create_server(host, port) nên TCP_NODELAY luôn bật.
    """
    out = []
    for w in (1, 2, 3, 4):
        for nodelay in ((True,) if w == 1 else (False, True)):
            p = start_server(workers=w, env_extra={"FORCE_NODELAY": "1"} if (nodelay and w > 1) else None)
            try:
                for ep in ("/invoices", "/invoices/sync"):
                    r = load("closed", ep, c=32, d=5, body=True)
                    r.update(workers=w, endpoint=ep, nodelay=nodelay)
                    out.append(r)
                    log(f"e3 workers={w} nodelay={nodelay} {ep}", r)
            finally:
                stop(p)
    res["e3_workers"] = out


def e4_open_loop(res):
    """Latency theo mức tải (utilization) với service time cố định 2 ms CPU — so với lý thuyết hàng đợi."""
    p = start_server()
    out = []
    try:
        cap = load("closed", "/cpu/2", c=4, d=5)
        mu = cap["rps"]
        log("e4 capacity", cap)
        for rho in (0.2, 0.4, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95):
            r = load("open", "/cpu/2", r=rho * mu, d=8)
            r.update(rho_target=rho, mu=mu, service_ms=cap["p50"])
            out.append(r)
            log(f"e4 rho={rho}", r)
    finally:
        stop(p)
    res["e4_open_loop"] = out


def e5_deps(res):
    p = start_server()
    out = []
    try:
        load("closed", "/deps/0", c=10, d=2)  # warm-up
        for n in (0, 1, 5, 10, 20):
            r = load("closed", f"/deps/{n}", c=10, d=4)
            r.update(depth=n)
            out.append(r)
            log(f"e5 deps={n}", r)
    finally:
        stop(p)
    res["e5_deps"] = out


def e6_threads(res):
    """Giới hạn threadpool: def-endpoint với 40 (mặc định) vs 100 luồng."""
    out = []
    for th in ("40", "100"):
        p = start_server(env_extra={"THREADS": th})
        try:
            for c in (20, 40, 80, 160, 320):
                r = load("closed", "/io/sync", c=c, d=4)
                r.update(threads=int(th))
                out.append(r)
                log(f"e6 threads={th} c={c}", r)
        finally:
            stop(p)
    res["e6_threads"] = out


def e7_uvicorn_variants(res):
    """uvicorn thuần (h11 + asyncio) vs uvicorn[standard] (httptools + uvloop)."""
    out = []
    for http, loop in (("h11", "asyncio"), ("httptools", "asyncio"), ("h11", "uvloop"), ("httptools", "uvloop")):
        p = start_server(http=http, loop=loop)
        try:
            for ep, body in (("/health", False), ("/invoices", True)):
                r = load("closed", ep, c=32, d=5, body=body)
                r.update(http=http, loop=loop, endpoint=ep)
                out.append(r)
                log(f"e7 {http}+{loop} {ep}", r)
        finally:
            stop(p)
    res["e7_uvicorn_variants"] = out


EXPS = dict(e1=e1_io_modes, e2=e2_head_of_line, e3=e3_workers, e4=e4_open_loop, e5=e5_deps, e6=e6_threads, e7=e7_uvicorn_variants)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    sys.path.insert(0, str(HERE))
    from payload import payload_bytes
    BODY.parent.mkdir(exist_ok=True)
    BODY.write_bytes(payload_bytes(12))
    out_path = HERE / "results" / "concurrency.json"
    res = json.loads(out_path.read_text()) if out_path.exists() else {}
    res["machine"] = "4 vCPU Intel Xeon 2.8GHz, Python " + sys.version.split()[0]
    for k, fn in EXPS.items():
        if a.only and k not in a.only:
            continue
        fn(res)
        out_path.write_text(json.dumps(res, indent=1))
    print("→", out_path)


if __name__ == "__main__":
    main()
