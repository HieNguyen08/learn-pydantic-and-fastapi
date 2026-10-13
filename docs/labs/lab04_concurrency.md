# Lab 04 — Đo đồng thời: `async def`, `def` và chặn event loop

> ~20 phút · Sau Module 09 · Lời giải: `labs/lab04_concurrency/`

## Mục tiêu

Tái tạo kết quả trung tâm của Module 09 trên máy bạn: cùng một endpoint chờ I/O 50 ms, viết theo ba cách, cho ba trần thông lượng khác nhau, và **cả ba trần đều dự đoán được bằng định luật Little**.

## Bước 1 — Dự đoán

`app.py` có ba endpoint, mỗi cái chờ 50 ms:

| Endpoint | Cách viết | Trần dự đoán $X = N / W$ |
|---|---|---|
| `/io/async` | `async def` + `await asyncio.sleep` | $C / 0{,}05$ (tới khi CPU bão hòa) |
| `/io/sync` | `def` + `time.sleep` (threadpool 40 luồng) | $\min(C, 40) / 0{,}05 = 800$ req/s |
| `/io/blocking` | `async def` + `time.sleep` (chặn loop) | $1 / 0{,}05 = 20$ req/s |

Điền vào bảng: với $C = 100$ kết nối, mỗi endpoint đạt bao nhiêu req/s, và p50 bao nhiêu?

## Bước 2 — Chạy

```bash
cd labs/lab04_concurrency
python load.py --sweep          # tự khởi động uvicorn (uvloop + httptools), đo 3 endpoint × C ∈ {1, 10, 50, 100}
```

Cột `Little` là trần lý thuyết. Script dùng bộ sinh tải closed-loop của `scripts/bench/loadgen.py`.

Kết quả trên container 4 vCPU (uvicorn 1 tiến trình, uvloop + httptools):

```text
endpoint          C  đo req/s   Little  p50 ms  p99 ms
/io/async         1      19.3       20    51.6    52.2
/io/async        10     193.3      200    51.7    56.7
/io/async        50     963.7     1000    51.6    55.0
/io/async       100    1935.7     2000    51.5    56.3
/io/sync          1      19.0       20    52.1    54.6
/io/sync         10     190.0      200    52.3    56.7
/io/sync         50     755.0      800    64.4   103.9
/io/sync        100     776.7      800   127.6   141.8
/io/blocking      1      19.3       20    51.5    52.4
/io/blocking     10      19.7       20   459.0   919.5
/io/blocking     50      19.7       20  2496.8  2498.6
/io/blocking    100      19.7       20  5049.0  5055.3
```

Cả ba trần đều khớp định luật Little trong khoảng 3–6%: `async` tăng tuyến tính tới ~1.940 req/s, `sync` dừng ở ~780 req/s (trần 40 luồng), `blocking` dừng ở 20 req/s bất kể C.

## Bước 3 — Giải thích

1. `/io/sync` ở $C = 100$: thông lượng dừng gần 800 req/s và p50 tăng lên ~128 ms. Dùng Little để giải thích **p50**, không chỉ thông lượng: 100 request trong hệ thống, 40 đang chạy, 60 đang xếp hàng.
2. `/io/blocking`: vì sao p50 ở $C = 100$ là ~5 giây?
3. Trong lúc chạy `/io/blocking` với $C = 50$, gọi `curl http://127.0.0.1:<port>/health` ở terminal khác. Điều gì xảy ra, và vì sao một endpoint sai làm hỏng **mọi** endpoint khác (Module 09)?

## Mở rộng

- Nới threadpool lên 100 luồng (`anyio.to_thread.current_default_thread_limiter().total_tokens = 100` trong lifespan) và đo lại `/io/sync`. Trần có dịch đúng tới $100 / 0{,}05$ không?
- Chuyển sang tải **open-loop** (`run_open` trong `loadgen.py`) với λ = 0,8 × năng lực, và so p99 với công thức M/D/1 của Module 09.
