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

{{LAB04_OUTPUT}}

## Bước 3 — Giải thích

1. `/io/sync` ở $C = 100$: thông lượng dừng gần 800 req/s và p50 tăng lên ~125 ms. Dùng Little để giải thích **p50**, không chỉ thông lượng: 100 request trong hệ thống, 40 đang chạy, 60 đang xếp hàng.
2. `/io/blocking`: vì sao p50 ở $C = 100$ là ~5 giây?
3. Trong lúc chạy `/io/blocking` với $C = 50$, gọi `curl http://127.0.0.1:<port>/health` ở terminal khác. Điều gì xảy ra, và vì sao một endpoint sai làm hỏng **mọi** endpoint khác (Module 09)?

## Mở rộng

- Nới threadpool lên 100 luồng (`anyio.to_thread.current_default_thread_limiter().total_tokens = 100` trong lifespan) và đo lại `/io/sync`. Trần có dịch đúng tới $100 / 0{,}05$ không?
- Chuyển sang tải **open-loop** (`run_open` trong `loadgen.py`) với λ = 0,8 × năng lực, và so p99 với công thức M/D/1 của Module 09.
