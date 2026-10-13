# Module 09 — Async, đồng thời & hiệu năng

> Thời lượng: ~55 phút · Mức độ: Nâng cao · Tiên quyết: Module 02 (event loop, GIL), Module 07, Module 08

"Nên viết `async def` hay `def`?", "Chạy bao nhiêu worker?", "Vì sao CPU mới 40% mà latency đã tăng vọt?" — ba câu hỏi này quyết định một service FastAPI chịu được tải hay không, và chúng đều có câu trả lời **định lượng**. Module này làm ba việc: (1) **đo** ba cách viết handler dưới tải tăng dần và chỉ ra con số 40 luồng ẩn trong FastAPI; (2) dùng **lý thuyết hàng đợi** (định luật Little, M/M/1, M/D/1, M/M/c, Universal Scalability Law) để giải thích *mọi* đường cong đo được — kể cả một thí nghiệm open-loop khớp với mô hình M/D/1 sai lệch vài phần trăm; (3) kể lại một **cuộc điều tra hiệu năng thật** trong lúc viết khóa: vì sao `uvicorn --workers 2` lại *chậm* hơn 1 worker gần ba lần.

Mọi số đo chạy trên container 4 vCPU (bộ sinh tải chạy cùng máy), script `scripts/bench/bench_concurrency.py` (thí nghiệm e1–e9), Uvicorn 0.54, FastAPI 0.143, Python 3.13.

## Mục tiêu học tập

Sau module này, bạn có thể:

1. Giải thích cách FastAPI chạy `async def` (trên event loop) và `def` (threadpool anyio, **mặc định 40 luồng**), và dự đoán throughput tối đa của mỗi cách bằng **định luật Little**.
2. Nhận diện và đo tác hại của **lời gọi chặn trong `async def`** (head-of-line blocking).
3. Áp dụng **M/M/1, M/D/1, M/M/c (Erlang C)** để dự đoán latency theo mức tải, và giải thích vì sao latency tăng phi tuyến khi utilization vượt ~70%.
4. Phân biệt đo **closed-loop** và **open-loop**, và hiểu **coordinated omission**.
5. Dùng **Universal Scalability Law** để đọc đường cong throughput theo số worker.
6. Chẩn đoán một bất thường hiệu năng theo quy trình triệu chứng → giả thuyết → thí nghiệm → kết luận (case Nagle/`TCP_NODELAY`).
7. Lập **kế hoạch năng lực** (số worker, số luồng, giới hạn đồng thời, timeout) cho `invoice-api` và `ai-gateway`.

---

## 1. Hai cách FastAPI chạy handler

### 1.1. Cơ chế

- **`async def`**: FastAPI `await` hàm ngay trên **event loop**. Hàm phải nhường quyền (`await`) mỗi khi chờ I/O; trong lúc đó các coroutine khác chạy.
- **`def`**: FastAPI gọi `run_in_threadpool(func)` (Starlette → `anyio.to_thread.run_sync`). Hàm chạy trên một luồng của **threadpool mặc định của anyio**, có **giới hạn 40 luồng** (một `CapacityLimiter(40)`, đọc từ mã nguồn anyio). Luồng chờ I/O sẽ nhả GIL, event loop vẫn chạy.
- Quy tắc này áp dụng cho **cả handler lẫn dependency** (Module 08).

### 1.2. Thí nghiệm e1: ba cách chờ 50 ms

Ba endpoint cùng "chờ I/O" 50 ms:

```python
@app.get("/io/async")
async def io_async():
    await asyncio.sleep(0.05)      # nhường event loop

@app.get("/io/sync")
def io_sync():
    time.sleep(0.05)               # chạy trong threadpool — không chặn loop

@app.get("/io/blocking")
async def io_blocking():
    time.sleep(0.05)               # SAI: chặn cả event loop
```

Tải closed-loop với $C$ kết nối đồng thời (1 worker, h11 + asyncio):

| $C$ | `async` (req/s, p50) | `def` (req/s, p50) | `async` + chặn (req/s, p50) |
|---|---|---|---|
| 1 | 19 · 52 ms | 19 · 52 ms | 19 · 52 ms |
| 10 | 190 · 53 ms | 179 · 56 ms | **19,5 · 511 ms** |
| 40 | 760 · 53 ms | 548 · 72 ms | **19,5 · 2.047 ms** |
| 80 | 1.514 · 53 ms | **776 · 103 ms** | — |
| 160 | 2.239 · 71 ms | **768 · 208 ms** | — |
| 320 | 2.519 · 123 ms | **766 · 415 ms** | — |

<!-- placeholder-e1 -->

<!-- fig:e1 -->
<figure markdown="span">
  ![Số đo thật (e1): throughput và latency theo số kết nối đồng thời của ba cách chờ I/O 50 ms; đường chấm là trần tính bằng định luật Little](assets/figures/09/e1.light.svg#only-light){ loading=lazy }
  ![Số đo thật (e1): throughput và latency theo số kết nối đồng thời của ba cách chờ I/O 50 ms; đường chấm là trần tính bằng định luật Little](assets/figures/09/e1.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 9.1 — Số đo thật (e1): throughput và latency theo số kết nối đồng thời của ba cách chờ I/O 50 ms; đường chấm là trần tính bằng định luật Little.</figcaption>
</figure>
<!-- /fig -->

Ba đường cong, ba cơ chế giới hạn khác nhau — và cả ba đều tính được trước bằng định luật Little (mục 3):

- **`async`**: throughput tăng tuyến tính $X = C / 0{,}052$ cho tới khi **CPU** của worker bão hòa (~2.500 req/s ở $C = 320$; mỗi request vẫn tốn ~0,4 ms CPU cho HTTP + FastAPI).
- **`def`**: dừng ở **~770 req/s** bất kể $C$ — vì chỉ có 40 luồng, mỗi luồng giữ 52 ms: $X_{\max} = 40 / 0{,}052 \approx 770$. Request thứ 41 trở đi xếp hàng chờ luồng; p50 tăng tuyến tính theo $C$.
- **`async` + chặn**: dừng ở **~19,5 req/s** — chỉ có *một* event loop, mỗi request giữ nó 51 ms: $X_{\max} = 1 / 0{,}0513 \approx 19{,}5$. Với $C = 40$, mỗi request chờ 39 request khác: p50 ≈ 2 giây.

### 1.3. Thí nghiệm e2: một endpoint chặn làm hỏng mọi endpoint khác

Đo `GET /health` (không làm gì) bằng một kết nối, trong khi 20 kết nối khác gọi liên tục một endpoint khác:

| Tải nền | `/health` p50 | `/health` p99 |
|---|---|---|
| không có | 0,43 ms | 1,0 ms |
| 20 kết nối vào `/io/async` | 0,43 ms | 1,1 ms |
| 20 kết nối vào `/io/blocking` | **1.026 ms** | **1.030 ms** |

<!-- placeholder-e2 -->

<!-- fig:e2 -->
<figure markdown="span">
  ![Số đo thật (e2): latency của /health dưới ba loại tải nền](assets/figures/09/e2.light.svg#only-light){ loading=lazy }
  ![Số đo thật (e2): latency của /health dưới ba loại tải nền](assets/figures/09/e2.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 9.2 — Số đo thật (e2): latency của /health dưới ba loại tải nền.</figcaption>
</figure>
<!-- /fig -->

Gấp **~2.400 lần**. Đây là điều khiến lỗi "gọi thư viện đồng bộ trong `async def`" nguy hiểm: endpoint lỗi không chỉ chậm *chính nó* mà chậm **mọi** request trên cùng tiến trình — kể cả health check, khiến Kubernetes nghĩ pod chết và khởi động lại (Module 13). Thủ phạm thường gặp: `requests.get`, driver DB đồng bộ (`psycopg2`, `pymysql`), SDK đồng bộ của nhà cung cấp, `time.sleep`, đọc file lớn, băm mật khẩu, nén ảnh, `model_validate` trên payload khổng lồ (Module 06, mục 6).

### 1.4. Thí nghiệm e6: nới giới hạn threadpool

```python
@asynccontextmanager
async def lifespan(app):
    anyio.to_thread.current_default_thread_limiter().total_tokens = 100
    yield
```

| $C$ | 40 luồng (mặc định) | 100 luồng |
|---|---|---|
| 40 | 598 req/s | 603 req/s |
| 80 | 773 | 1.021 |
| 160 | 764 | **1.536** ≈ 100 / 0,065 |

<!-- placeholder-e6 -->

<!-- fig:e6 -->
<figure markdown="span">
  ![Số đo thật (e6): nới giới hạn threadpool từ 40 lên 100 luồng dịch trần throughput đúng như Little dự đoán](assets/figures/09/e6.light.svg#only-light){ loading=lazy }
  ![Số đo thật (e6): nới giới hạn threadpool từ 40 lên 100 luồng dịch trần throughput đúng như Little dự đoán](assets/figures/09/e6.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 9.3 — Số đo thật (e6): nới giới hạn threadpool từ 40 lên 100 luồng dịch trần throughput đúng như Little dự đoán.</figcaption>
</figure>
<!-- /fig -->

Nới giới hạn có tác dụng, nhưng đó là **chữa triệu chứng**: mỗi luồng tốn ~16 KB RSS và chi phí chuyển ngữ cảnh (Module 02), luồng CPU-bound vẫn tranh nhau một GIL. Lời giải gốc cho I/O là thư viện **async** (`httpx.AsyncClient`, `asyncpg`, SQLAlchemy async — Module 10).

### 1.5. Quy tắc chọn

| Handler/dependency làm gì | Viết | Vì sao |
|---|---|---|
| I/O bằng thư viện async | `async def` + `await` | rẻ nhất, mở rộng tới hàng nghìn request đồng thời |
| I/O bằng thư viện **đồng bộ** | `def` | không chặn loop; giới hạn 40 luồng → tính bằng Little |
| CPU ngắn (< ~1 ms) | `async def` | tránh chi phí threadpool (~65 µs/lần, Module 08) |
| CPU dài (băm mật khẩu, validate batch lớn, xử lý ảnh) | `def` hoặc `await run_in_threadpool(...)`; nặng hơn nữa → tiến trình/worker riêng | không chặn loop; GIL vẫn giới hạn song song |
| Không chắc thư viện có chặn không | đo bằng thí nghiệm e2 (latency `/health` dưới tải) | |

Chế độ debug của asyncio (`PYTHONASYNCIODEBUG=1` hoặc `loop.set_debug(True)`) ghi cảnh báo mỗi khi một callback giữ loop quá `slow_callback_duration` (mặc định 100 ms) — một cách rẻ để bắt lời gọi chặn trong môi trường test.

---

## 2. Thí nghiệm e4: latency theo mức tải

### 2.1. Closed-loop, open-loop và coordinated omission

Các thí nghiệm e1–e3 là **closed-loop**: $C$ client, mỗi client chờ response rồi mới gửi tiếp. Khi server chậm, client tự gửi chậm lại — tải tự giảm. Người dùng thật thì không như vậy: 12.000 máy POS gửi hóa đơn theo nhịp bán hàng, không chờ nhau. Đo closed-loop vì thế **che** latency đuôi: những request lẽ ra phải gửi trong lúc server đang nghẽn bị trì hoãn, và thời gian chờ đó không được tính — hiện tượng Gil Tene gọi là **coordinated omission**.

Thí nghiệm e4 dùng **open-loop**: request đến theo quá trình Poisson tốc độ $\lambda$ không phụ thuộc server, và latency tính từ **thời điểm lẽ ra phải gửi** (`loadgen.py`, chế độ `open`). Endpoint `/cpu/2` đốt đúng 2 ms CPU trên event loop — một "máy phục vụ" có thời gian phục vụ gần như cố định. Năng lực đo bằng closed-loop: $\mu \approx 402$ req/s, tức thời gian phục vụ $S = 1/\mu \approx 2{,}49$ ms (2 ms tính toán + ~0,5 ms HTTP/FastAPI).

### 2.2. Kết quả

| $\rho = \lambda/\mu$ (đạt được) | 0,20 | 0,39 | 0,60 | 0,70 | 0,79 | 0,84 | 0,90 | 0,94 |
|---|---|---|---|---|---|---|---|---|
| latency trung bình (ms) | 4,8 | 4,6 | 5,7 | 6,8 | 9,4 | 10,9 | 15,4 | 24,9 |
| p99 (ms) | 14,3 | 10,0 | 15,7 | 18,6 | 29,0 | 34,3 | 54,8 | 77,2 |

<!-- placeholder-e4 -->

<!-- fig:e4 -->
<figure markdown="span">
  ![Số đo thật (e4, open-loop): latency trung bình, p50, p99 theo utilization](assets/figures/09/e4.light.svg#only-light){ loading=lazy }
  ![Số đo thật (e4, open-loop): latency trung bình, p50, p99 theo utilization](assets/figures/09/e4.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 9.4 — Số đo thật (e4, open-loop): latency trung bình, p50, p99 theo utilization.</figcaption>
</figure>
<!-- /fig -->

Từ $\rho = 0{,}2$ đến $0{,}7$, latency trung bình chỉ tăng 2 ms. Từ $0{,}7$ đến $0{,}94$ — tức thêm chưa tới 100 req/s — latency trung bình tăng **3,7 lần**, p99 tăng **4 lần**. CPU lúc đó vẫn "chưa đầy". Phần tiếp theo giải thích vì sao bằng toán, và mô hình dự đoán đúng các con số này.

---

## 3. Lý thuyết hàng đợi cho kỹ sư backend

### 3.1. Định luật Little

Với một hệ ổn định bất kỳ (không cần giả định phân phối), gọi $\lambda$ là tốc độ đến trung bình, $W$ thời gian trung bình một yêu cầu ở trong hệ, $L$ số yêu cầu trung bình đang ở trong hệ:

$$
L = \lambda W.
$$

(Little, *Operations Research* 1961.) Trực giác: nếu mỗi giây có $\lambda$ khách vào và mỗi khách ở lại $W$ giây, thì bất kỳ lúc nào cũng có $\lambda W$ khách bên trong. Dạng nghịch đảo dùng để tính **throughput tối đa** khi số "chỗ" $L_{\max}$ bị giới hạn:

$$
X_{\max} = \frac{L_{\max}}{W}.
$$

Đây chính là ba trần ở mục 1.2: 40 luồng / 52 ms ≈ 770 req/s; 1 event loop / 51 ms ≈ 19,5 req/s; và mục 1.4: 100 luồng / 65 ms ≈ 1.540 req/s. Định luật Little dùng ở **mọi** tầng: số kết nối DB cần (Module 10), số worker, số request LLM đồng thời.

### 3.2. M/M/1 và M/D/1

Mô hình một máy phục vụ, khách đến Poisson tốc độ $\lambda$, thời gian phục vụ trung bình $S = 1/\mu$, utilization $\rho = \lambda/\mu < 1$:

- **M/M/1** (thời gian phục vụ phân phối mũ): thời gian trong hệ trung bình
  $$
  W = \frac{S}{1 - \rho}.
  $$
- **M/D/1** (thời gian phục vụ cố định — gần với endpoint `/cpu/2`): công thức Pollaczek–Khinchine cho
  $$
  W = S + \frac{\rho\, S}{2(1 - \rho)}.
  $$

Cả hai có chung mẫu số $1 - \rho$: khi $\rho \to 1$, thời gian chờ **tiến tới vô cùng**. Ví dụ số với $S = 2{,}49$ ms (M/D/1): $\rho = 0{,}5 \Rightarrow W = 3{,}7$ ms; $\rho = 0{,}8 \Rightarrow W = 7{,}5$ ms; $\rho = 0{,}9 \Rightarrow W = 13{,}7$ ms; $\rho = 0{,}95 \Rightarrow W = 26{,}1$ ms. Mỗi lần khoảng cách tới 100% giảm một nửa, thời gian chờ **gấp đôi**.

### 3.3. Đối chiếu với số đo

Latency đo được gồm thời gian trong server **cộng** một hằng số $\delta$ (bộ sinh tải, loopback TCP). Ước lượng $\delta \approx 2$ ms từ điểm $\rho = 0{,}2$, rồi so mô hình với số đo ở các mức tải cao (dùng $\rho$ thực đạt được):

| $\rho$ | M/D/1 + $\delta$ | M/M/1 + $\delta$ | đo được |
|---|---|---|---|
| 0,79 | 9,2 ms | 14,0 ms | 9,4 ms |
| 0,84 | 11,0 ms | 17,5 ms | 10,9 ms |
| 0,90 | 15,6 ms | 26,6 ms | **15,4 ms** |
| 0,945 | 25,8 ms | 47,1 ms | **24,9 ms** |

<!-- placeholder-theory -->

<!-- fig:theory -->
<figure markdown="span">
  ![Đối chiếu số đo e4 với lý thuyết hàng đợi: trung bình so với M/D/1 và M/M/1 (trái); p99 so với mô phỏng M/D/1 (phải)](assets/figures/09/theory.light.svg#only-light){ loading=lazy }
  ![Đối chiếu số đo e4 với lý thuyết hàng đợi: trung bình so với M/D/1 và M/M/1 (trái); p99 so với mô phỏng M/D/1 (phải)](assets/figures/09/theory.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 9.5 — Đối chiếu số đo e4 với lý thuyết hàng đợi: trung bình so với M/D/1 và M/M/1 (trái); p99 so với mô phỏng M/D/1 (phải).</figcaption>
</figure>
<!-- /fig -->

M/D/1 khớp trong vài phần trăm; ngay cả p99 cũng khớp với mô phỏng M/D/1 bằng phương trình Lindley (hình bên phải) ở dải $\rho$ từ 0,4 đến 0,9. M/M/1 bi quan gần gấp đôi vì giả định thời gian phục vụ biến thiên mạnh. Bài học: **độ biến thiên của thời gian phục vụ** cũng quan trọng như giá trị trung bình — endpoint có latency lúc nhanh lúc chậm (cache hit/miss, payload to nhỏ) xếp hàng tệ hơn endpoint đều đặn có cùng trung bình. Công thức Pollaczek–Khinchine tổng quát (M/G/1) nói chính xác điều đó: thời gian chờ tỷ lệ với $(1 + C_s^2)/2$, trong đó $C_s$ là hệ số biến thiên của thời gian phục vụ.

**Quy tắc vận hành**: đặt mục tiêu utilization **≤ 60–70%** cho tài nguyên nằm trên đường đi của request có SLO latency. Vượt mức đó, một đợt tăng tải nhỏ biến thành latency đuôi lớn.

### 3.4. Nhiều máy phục vụ: M/M/c và Erlang C

Với $c$ worker giống nhau và một hàng đợi chung, xác suất một request phải chờ là công thức **Erlang C** (với $a = \lambda S$ là tải tính bằng erlang, $\rho = a/c$):

$$
P_{\text{chờ}} = \frac{\dfrac{a^c}{c!}\dfrac{c}{c - a}}{\displaystyle\sum_{k=0}^{c-1}\frac{a^k}{k!} + \dfrac{a^c}{c!}\dfrac{c}{c - a}}, \qquad
W_q = \frac{P_{\text{chờ}}\, S}{c - a}.
$$

Hệ quả quan trọng: **gộp tài nguyên** giảm thời gian chờ. Hai worker dùng chung một hàng đợi có latency tốt hơn hẳn hai worker mỗi cái một hàng đợi riêng ở cùng tổng tải — một lý do để cân bằng tải tới các pod theo "ít kết nối nhất" thay vì ngẫu nhiên.

Áp vào CPU của `invoice-api`: 500 req/s, mỗi request ~0,5 ms CPU (h11) → $a = 0{,}25$ erlang. Với $c = 1$: $P_{\text{chờ}} = 0{,}25$, $W_q \approx 0{,}17$ ms; với $c = 2$: $P_{\text{chờ}} \approx 0{,}03$. CPU **không** phải nút thắt của `invoice-api` ở tải thiết kế — nút thắt nằm ở database (Module 10). Nhiều worker/pod ở đây chủ yếu để **chịu lỗi** và hấp thụ burst, không phải vì thiếu CPU.

### 3.5. Đuôi phân phối khi fan-out

Dean & Barroso (*The Tail at Scale*, CACM 2013): nếu một request phải chờ $n$ thành phần song song và mỗi thành phần có xác suất $p$ chậm, xác suất request chậm là $1 - (1-p)^n$. Với $p = 1\%$ và $n = 100$: $1 - 0{,}99^{100} \approx 63\%$. Với `ai-gateway`, một lượt chạy gọi tuần tự 3–4 dịch vụ (retrieval, LLM, kiểm chứng) — latency đuôi của từng bước **cộng dồn**. Kỹ thuật giảm đuôi từ bài báo: hedged request (gửi bản sao sau một ngưỡng thời gian), timeout theo ngân sách, bỏ bớt phần không thiết yếu khi trễ.

---

## 4. Nhiều tiến trình: worker, USL và cuộc điều tra 40 ms

### 4.1. Thí nghiệm e3 và một bất thường

`POST /invoices` (hóa đơn 12 dòng), 32 kết nối, tăng số worker Uvicorn (`--workers N`, h11 + asyncio):

| worker | 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| req/s | 2.048 | **705** | **708** | **701** |
| p50 | 14,6 ms | **44,1 ms** | 44,1 ms | 44,1 ms |

Thêm worker làm throughput **giảm gần ba lần**, và p50 dính chặt ở **44 ms** bất kể số worker. Không có tài nguyên nào bão hòa (mỗi tiến trình ~15–20% CPU).

### 4.2. Điều tra

1. **Triệu chứng đặc trưng**: một con số latency cố định (~40–44 ms) độc lập với tải và số worker → nghi một **bộ đếm thời gian** chứ không phải tranh chấp tài nguyên. Trên Linux, ~40 ms là thời gian **delayed ACK** mặc định của TCP.
2. **Giả thuyết**: thuật toán Nagle (gom gói nhỏ, chờ ACK trước khi gửi gói tiếp) + delayed ACK của phía nhận. Uvicorn ghi header và body response bằng **hai** lần `write`; nếu socket không bật `TCP_NODELAY`, phần body chờ ACK của phần header, và client trì hoãn ACK ~40 ms.
3. **Kiểm tra với 1 kết nối**: `GET /health`, 1 kết nối: 1 worker 0,49 ms; 2 worker **44 ms** → không liên quan tải; xác nhận cơ chế theo-từng-request.
4. **Tìm nguyên nhân trong mã**: asyncio chỉ bật `TCP_NODELAY` cho socket có `proto == IPPROTO_TCP` (`asyncio.base_events._set_nodelay`). Với 1 worker, Uvicorn tạo socket qua `loop.create_server(host, port)` (qua `getaddrinfo`, `proto = 6`). Với `--workers`, tiến trình cha tạo socket bằng `socket.socket(AF_INET, SOCK_STREAM)` — **`proto = 0`** (kiểm chứng trực tiếp) — rồi chia cho tiến trình con; mọi kết nối được accept kế thừa `proto = 0`, nên asyncio **bỏ qua** `TCP_NODELAY`.
5. **Thí nghiệm kiểm chứng**: vá `_set_nodelay` để bật `TCP_NODELAY` bất kể `proto` (biến môi trường `FORCE_NODELAY` trong `bench_app.py`):

| worker | 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| mặc định (req/s) | 2.048 | 705 | 708 | 701 |
| ép `TCP_NODELAY` (req/s) | 2.048 | **3.516** | **5.380** | **5.563** |

6. **Phạm vi** (thí nghiệm e9, 1 kết nối, p50 của `/health`):

| vòng lặp | 1 worker | 2 worker |
|---|---|---|
| asyncio (h11 hoặc httptools) | 0,2 ms | **44 ms** |
| uvloop | 0,2 ms | 0,2 ms |

uvloop bật `TCP_NODELAY` cho mọi socket TCP nên không bị ảnh hưởng.

<!-- placeholder-nagle -->

<!-- fig:nagle -->
<figure markdown="span">
  ![Số đo thật: thêm worker làm chậm đi do Nagle + delayed ACK (e3); chỉ tổ hợp vòng lặp asyncio với --workers bị ảnh hưởng (e9)](assets/figures/09/nagle.light.svg#only-light){ loading=lazy }
  ![Số đo thật: thêm worker làm chậm đi do Nagle + delayed ACK (e3); chỉ tổ hợp vòng lặp asyncio với --workers bị ảnh hưởng (e9)](assets/figures/09/nagle.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 9.6 — Số đo thật: thêm worker làm chậm đi do Nagle + delayed ACK (e3); chỉ tổ hợp vòng lặp asyncio với --workers bị ảnh hưởng (e9).</figcaption>
</figure>
<!-- /fig -->

**Kết luận thực hành**: chạy `--workers` với vòng lặp asyncio thuần (tức cài `uvicorn` không kèm `[standard]`) trên Linux có thể làm mỗi response chậm thêm ~40 ms. Cài `uvicorn[standard]` (uvloop) — hoặc mô hình một tiến trình mỗi container (Module 13) — tránh được. Quan trọng hơn con số: **một latency cố định, độc lập với tải là dấu vân tay của một bộ hẹn giờ**, không phải của thiếu tài nguyên; đừng thêm máy để chữa nó.

### 4.3. Universal Scalability Law

Gunther mô hình hóa throughput theo số đơn vị song song $N$:

$$
X(N) = \frac{\lambda N}{1 + \sigma (N - 1) + \kappa N (N - 1)},
$$

trong đó $\sigma$ là phần **tranh chấp** (hàng đợi trên tài nguyên chung — dạng Amdahl), $\kappa$ là chi phí **đồng bộ/nhất quán** giữa các đơn vị (tăng theo số cặp). Khớp với dữ liệu đã sửa `TCP_NODELAY`: $\sigma \approx 0$, $\kappa \approx 0{,}037$, đỉnh ở $N^* = \sqrt{(1-\sigma)/\kappa} \approx 5$.

<!-- placeholder-usl -->

<!-- fig:usl -->
<figure markdown="span">
  ![Universal Scalability Law khớp với throughput theo số worker sau khi đã sửa TCPNODELAY](assets/figures/09/usl.light.svg#only-light){ loading=lazy }
  ![Universal Scalability Law khớp với throughput theo số worker sau khi đã sửa TCPNODELAY](assets/figures/09/usl.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 9.7 — Universal Scalability Law khớp với throughput theo số worker sau khi đã sửa TCP_NODELAY.</figcaption>
</figure>
<!-- /fig -->

Đọc cẩn thận: trên máy đo, **bộ sinh tải chạy chung 4 vCPU với server**, nên từ 3 lên 4 worker các tiến trình tranh CPU với chính client — $\kappa$ ở đây phần lớn là "tranh CPU với máy đo", không phải chi phí của Uvicorn. Trên máy riêng, đường cong thẳng hơn nhiều cho tới số core vật lý. Cách dùng USL đúng: đo ở 3–5 điểm, khớp $\sigma$, $\kappa$, và dùng $N^*$ để biết **thêm worker từ đâu trở đi là vô ích hoặc có hại**.

### 4.4. Bao nhiêu worker?

| Ngữ cảnh | Khuyến nghị |
|---|---|
| Kubernetes/container | **1 tiến trình Uvicorn mỗi container**, scale bằng số pod (HPA); request/limit CPU ~1 core. Đơn giản hóa health check, log, graceful shutdown (Module 13). |
| Máy ảo/bare metal | `--workers` ≈ số core cho service CPU-bound; với I/O-bound async thường ít hơn (1–2 đã đủ để dùng hết core khi phần lớn là chờ). |
| Luôn | `uvicorn[standard]`; đo bằng tải open-loop ở $\rho$ mục tiêu ~0,6. |

---

## 5. Kiểm soát đồng thời: backpressure và timeout

### 5.1. Vấn đề

Một service không giới hạn sẽ nhận **mọi** request đến, kể cả khi đã quá tải. Hàng đợi nội bộ phình ra, latency của mọi request tăng (mục 3.2), client hết thời gian chờ và **gửi lại** — tải thật tăng gấp đôi đúng lúc hệ đang yếu nhất. Đây là cơ chế của *metastable failure* (Module 13). Phòng thủ là **giới hạn có chủ đích** ở mọi tầng.

### 5.2. Các công cụ

```python
import asyncio
import httpx

LLM_LIMIT = asyncio.Semaphore(20)              # ≤ 20 lượt gọi LLM đồng thời mỗi tiến trình
llm = httpx.AsyncClient(timeout=httpx.Timeout(connect=2.0, read=30.0, write=5.0, pool=1.0))

async def call_llm(payload: dict) -> dict:
    try:
        async with asyncio.timeout(0.5):       # chờ "chỗ" tối đa 0,5 s, quá thì từ chối ngay
            await LLM_LIMIT.acquire()
    except TimeoutError:
        raise HTTPException(503, "Quá tải, thử lại sau", headers={"Retry-After": "5"})
    try:
        r = await llm.post("/v1/chat/completions", json=payload)
        r.raise_for_status()
        return r.json()
    finally:
        LLM_LIMIT.release()
```

| Tầng | Cơ chế | Giá trị cho `invoice-api` / `ai-gateway` |
|---|---|---|
| Server | `uvicorn --limit-concurrency N` → 503 khi vượt; `--backlog` | invoice-api: N ≈ 4 × L dự kiến mỗi tiến trình |
| Handler | `asyncio.Semaphore` quanh tài nguyên khan hiếm (LLM, API bên thứ ba) | ai-gateway: 20 lượt LLM/tiến trình |
| Client đi ra | timeout `connect`/`read`/`pool` tường minh (httpx mặc định 5 s cho mọi loại) | LLM read 30 s; Zendesk API 10 s |
| Toàn request | `asyncio.timeout(...)` theo ngân sách latency | invoice-api 2 s; ai-gateway 60 s |
| DB | pool size + `pool_timeout` (Module 10) | |

Nguyên tắc: **từ chối sớm và rõ ràng** (503 + `Retry-After`) tốt hơn nhận rồi xử lý chậm cho tất cả.

---

## 6. Case Mekong Cloud: kế hoạch năng lực

### 6.1. `invoice-api`

- Tải thiết kế 500 req/s. Thời gian mỗi request (ước lượng): ~0,25 ms CPU (`uvicorn[standard]`) + ~5 ms chờ DB (transaction ghi hóa đơn, Module 10) → $W \approx 6$ ms.
- **Little**: $L = 500 \times 0{,}006 = 3$ request đồng thời trên toàn hệ. Rất ít — và đó là lý do handler `async def` với driver async là đủ, không cần threadpool lớn.
- **CPU**: $a = 500 \times 0{,}25\text{ ms} = 0{,}125$ core. Mục tiêu $\rho \le 0{,}6$ trên mỗi pod 1 core → 1 pod là đủ về CPU; chạy **3 pod** (mỗi pod 1 tiến trình) để chịu mất một zone và hấp thụ burst cuối tháng.
- **Kết nối DB**: $L_{\text{DB}} = 500 \times 0{,}005 = 2{,}5$ kết nối bận trung bình → pool 5–10 mỗi pod là thừa (Module 10 tính kỹ hơn).
- **Giới hạn**: `--limit-concurrency 200` mỗi tiến trình, timeout request 2 s.

### 6.2. `ai-gateway`

- Đỉnh 0,4 lượt chạy/giây, mỗi lượt ~15 s (chủ yếu chờ LLM) → $L = 6$ lượt đồng thời; burst ×3 → 18.
- Mọi I/O async (`httpx.AsyncClient`, Redis async) → **một** event loop phục vụ được hàng trăm lượt chờ; 2 pod để chịu lỗi.
- Semaphore LLM 20/tiến trình (khớp hạn mức của nhà cung cấp), timeout đọc 30 s, timeout toàn lượt 60 s.
- 60 kết nối SSE mở lâu: ~60 coroutine (~1 KB mỗi cái, Module 02) — không đáng kể; nhưng load balancer thường đóng kết nối rảnh sau 60 s → gửi dòng comment `: ping` mỗi 15 s.

<!-- placeholder-capacity -->

<!-- fig:capacity -->
<figure markdown="span">
  ![Kế hoạch năng lực của hai dịch vụ, tính bằng định luật Little và mục tiêu utilization](assets/figures/09/capacity.light.svg#only-light){ loading=lazy }
  ![Kế hoạch năng lực của hai dịch vụ, tính bằng định luật Little và mục tiêu utilization](assets/figures/09/capacity.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 9.8 — Kế hoạch năng lực của hai dịch vụ, tính bằng định luật Little và mục tiêu utilization.</figcaption>
</figure>
<!-- /fig -->

---

## Lỗi thường gặp & cách xử lý

| Triệu chứng | Nguyên nhân gốc | Cách xử lý |
|---|---|---|
| Throughput dừng ở ~X req/s dù tăng client, CPU thấp | `def` handler, 40 luồng / thời gian chờ | Thư viện async; hoặc tính và nới giới hạn threadpool |
| Mọi endpoint (cả `/health`) chậm khi một endpoint bị gọi nhiều | Lời gọi chặn trong `async def` | Đổi sang `def` / thư viện async; bật asyncio debug trong test |
| Latency tăng vọt khi CPU mới ~70–80% | Hàng đợi: $W \propto 1/(1-\rho)$ | Mục tiêu $\rho \le 0{,}6$–$0{,}7$; scale sớm |
| Benchmark đẹp nhưng production có p99 xấu | Đo closed-loop (coordinated omission) | Đo open-loop theo tốc độ đến; tính latency từ thời điểm dự kiến |
| Thêm worker mà chậm hơn, latency cố định ~40 ms | Nagle + delayed ACK (asyncio + `--workers` trên Linux) | `uvicorn[standard]` (uvloop) hoặc 1 tiến trình/container |
| Thêm worker không tăng throughput | Tranh chấp tài nguyên chung (USL: $\sigma$, $\kappa$) | Đo, khớp USL, dừng ở $N^*$; tìm tài nguyên chung |
| Quá tải → client retry → sập hẳn | Không giới hạn đồng thời, không timeout | Semaphore, `--limit-concurrency`, timeout, 503 + `Retry-After` |

## Tóm tắt (cheat-sheet)

- `async def` → event loop; `def` → threadpool anyio **40 luồng**. Quy tắc áp dụng cho cả dependency.
- Đo được (chờ 50 ms): async tăng tới khi hết CPU (~2.500 req/s); `def` trần **~770** = 40/0,052; async-chặn trần **~19,5** = 1/0,051 và làm `/health` chậm **~2.400×**.
- **Little**: $L = \lambda W$, $X_{\max} = L_{\max}/W$ — dùng cho luồng, worker, kết nối DB, lượt LLM.
- **M/D/1**: $W = S + \rho S/(2(1-\rho))$ — khớp số đo open-loop trong vài phần trăm; **M/M/1**: $W = S/(1-\rho)$. Giữ $\rho \le 0{,}6$–$0{,}7$.
- **Erlang C**: gộp tài nguyên giảm thời gian chờ; CPU của `invoice-api` chỉ ~0,125 core ở tải thiết kế.
- Đo **open-loop** để tránh coordinated omission.
- `--workers` + asyncio thuần trên Linux: +~40 ms mỗi response (Nagle). uvloop không bị.
- **USL**: $X(N) = \lambda N / (1 + \sigma(N-1) + \kappa N(N-1))$; $N^* = \sqrt{(1-\sigma)/\kappa}$.
- Giới hạn có chủ đích: semaphore, `--limit-concurrency`, timeout tường minh, 503 + `Retry-After`.

## Câu hỏi tự kiểm tra / phỏng vấn

1. Endpoint `def` gọi một API bên ngoài mất 200 ms. Throughput tối đa của một worker FastAPI mặc định là bao nhiêu? Làm sao tăng?

    <details markdown="1"><summary>Gợi ý</summary>
    $X_{\max} = 40 / 0{,}2 = 200$ req/s (Little, 40 luồng). Tăng: dùng `httpx.AsyncClient` + `async def` (giới hạn chuyển sang CPU/kết nối), hoặc nới threadpool (tạm thời), hoặc thêm worker/pod.
    </details>

2. Vì sao `time.sleep(0.05)` trong `async def` làm `/health` chậm tới 1 giây khi có 20 kết nối?

    <details markdown="1"><summary>Gợi ý</summary>
    Event loop bị chặn 50 ms mỗi request; 20 request xếp hàng tuần tự → một request `/health` phải chờ ~20 × 51 ms ≈ 1 s. Mọi coroutine trên loop đều chờ.
    </details>

3. Phát biểu định luật Little. Dùng nó tính số kết nối DB cần cho 500 req/s, mỗi request giữ kết nối 8 ms.

    <details markdown="1"><summary>Gợi ý</summary>
    $L = \lambda W$. $L = 500 \times 0{,}008 = 4$ kết nối bận trung bình; cộng dư cho biến động và burst (ví dụ ×2–3) → pool ~10.
    </details>

4. Server có $S = 10$ ms. So latency trung bình ở $\rho = 0{,}5$ và $0{,}9$ theo M/M/1 và M/D/1.

    <details markdown="1"><summary>Gợi ý</summary>
    M/M/1: 20 ms và 100 ms. M/D/1: $10 + 0{,}5\cdot10/(2\cdot0{,}5) = 15$ ms và $10 + 0{,}9\cdot10/0{,}2 = 55$ ms.
    </details>

5. Coordinated omission là gì? Vì sao benchmark closed-loop đánh giá thấp latency đuôi?

    <details markdown="1"><summary>Gợi ý</summary>
    Khi server chậm, client closed-loop tự gửi chậm lại, nên các request lẽ ra đến trong lúc nghẽn không được gửi/không được tính thời gian chờ. Open-loop gửi theo lịch độc lập và tính latency từ thời điểm dự kiến.
    </details>

6. Throughput giảm khi thêm worker và latency dính ở ~40 ms. Bạn nghi gì đầu tiên và kiểm chứng thế nào?

    <details markdown="1"><summary>Gợi ý</summary>
    Latency cố định độc lập tải → bộ hẹn giờ; 40 ms → delayed ACK + Nagle. Kiểm chứng: đo với 1 kết nối (vẫn ~40 ms), kiểm tra `TCP_NODELAY` trên socket, thử uvloop hoặc ép NODELAY.
    </details>

7. Giải thích hai tham số $\sigma$, $\kappa$ của USL và ý nghĩa của $N^*$.

    <details markdown="1"><summary>Gợi ý</summary>
    $\sigma$: tranh chấp (phần tuần tự, hàng đợi trên tài nguyên chung) làm throughput bão hòa; $\kappa$: chi phí đồng bộ/nhất quán theo cặp làm throughput **giảm** sau đỉnh. $N^* = \sqrt{(1-\sigma)/\kappa}$ là số đơn vị cho throughput lớn nhất.
    </details>

8. Thiết kế giới hạn đồng thời cho `ai-gateway` khi nhà cung cấp LLM cho phép 50 request đồng thời và có 2 pod.

    <details markdown="1"><summary>Gợi ý</summary>
    Semaphore ~20–25 mỗi pod (tổng < 50, chừa biên); chờ semaphore có timeout ngắn rồi trả 503 + Retry-After; timeout đọc LLM 30 s; timeout toàn lượt 60 s; webhook Zendesk trả nhanh và đẩy việc vào hàng đợi (Module 13–14).
    </details>

## Bài tập thực hành

1. **Tái tạo e1, e2 (CPU, 20 phút).** Làm theo Lab 04; vẽ throughput theo $C$ cho ba cách viết và đánh dấu ba trần tính bằng Little.
2. **Kiểm chứng M/D/1 (CPU, 20 phút).** Chạy `bench_concurrency.py --only e4`, rồi đổi `/cpu/2` thành thời gian phục vụ ngẫu nhiên (phân phối mũ trung bình 2 ms). So với M/M/1.
3. **Erlang C (giấy/CPU, 15 phút).** Viết hàm Erlang C, tính $P_{\text{chờ}}$ khi `ai-gateway` có $a = 6$ lượt LLM và semaphore $c = 8, 10, 20$.
4. **Bắt lời gọi chặn (CPU, 15 phút).** Bật `PYTHONASYNCIODEBUG=1`, gọi một endpoint `async def` có `requests.get(...)`; đọc cảnh báo "Executing … took … seconds".

## Tài liệu tham khảo

Paper và sách:

- Little, J. D. C. (1961). *A Proof for the Queuing Formula: L = λW*. Operations Research 9(3), 383–387.
- Kleinrock, L. (1975). *Queueing Systems, Volume 1: Theory*. Wiley — M/M/1, M/M/c, M/G/1 (Pollaczek–Khinchine).
- Harchol-Balter, M. (2013). *Performance Modeling and Design of Computer Systems: Queueing Theory in Action*. Cambridge University Press.
- Gunther, N. J. (2007). *Guerrilla Capacity Planning*. Springer — Universal Scalability Law.
- Dean, J., Barroso, L. A. (2013). *The Tail at Scale*. Communications of the ACM 56(2), 74–80.
- Nagle, J. (1984). *RFC 896: Congestion Control in IP/TCP Internetworks*. https://www.rfc-editor.org/rfc/rfc896
- Braden, R. (1989). *RFC 1122: Requirements for Internet Hosts* (delayed ACK). https://www.rfc-editor.org/rfc/rfc1122
- Tene, G. *How NOT to Measure Latency* (bài nói, coordinated omission). https://www.youtube.com/watch?v=lJ8ydIuPFeU

Tài liệu chính thức (tra cứu 10/2026):

- FastAPI — *Concurrency and async / await*. https://fastapi.tiangolo.com/async/
- anyio — *Working with threads* (`CapacityLimiter`, giới hạn mặc định). https://anyio.readthedocs.io/en/stable/threads.html
- Python docs — *Developing with asyncio* (debug mode, slow callbacks). https://docs.python.org/3/library/asyncio-dev.html
- Uvicorn — *Settings* (`--workers`, `--limit-concurrency`, `--loop`). https://www.uvicorn.org/settings/
- HTTPX — *Timeouts*. https://www.python-httpx.org/advanced/timeouts/
