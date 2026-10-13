# Module 13 — Production & observability

> Thời lượng: ~50 phút · Mức độ: Trung bình → Nâng cao · Tiên quyết: Module 09, 10, 12

Code đúng và nhanh trên máy dev mới là một nửa công việc. Nửa còn lại xảy ra lúc 19:00 ngày cuối tháng, khi `invoice-api` nhận 420 req/s, một node Kubernetes bị thay, database chậm 10 giây vì autovacuum, và 12.000 máy POS đồng loạt retry. Module này nói về **vận hành**:

- chạy service thế nào (process model, probe, tắt máy êm);
- **nhìn thấy** nó ra sao (log, metric, trace, và cái giá của chúng);
- đặt mục tiêu bằng số (SLO, error budget);
- và đối xử với lỗi thế nào để một sự cố nhỏ không biến thành sập hẳn (retry, backoff, metastable failure, load shedding).

Số đo trong `scripts/bench/bench_production.py`: uvicorn 0.54, FastAPI 0.143 (có **OpenTelemetry tích hợp sẵn**), opentelemetry-sdk 1.45. Hai thí nghiệm (p2, p3) là **mô phỏng** và được ghi rõ như vậy.

## Mục tiêu học tập

Sau module này, bạn có thể:

1. Chọn **process model** (một tiến trình mỗi pod hay nhiều worker) và cấu hình **liveness / readiness / startup probe** cùng **graceful shutdown** để rolling deploy không làm rơi request.
2. Thiết kế **ba trụ quan sát**: log có cấu trúc với correlation ID, metric RED/USE dạng histogram, trace OpenTelemetry. Định lượng được chi phí mỗi thứ và biết bật telemetry tích hợp của FastAPI.
3. Tính toán đúng với **percentile**: không lấy trung bình các p99, và chọn bucket histogram theo SLO.
4. Đặt **SLO**, tính **error budget** và cảnh báo theo **burn rate** nhiều cửa sổ.
5. Dùng **timeout, retry với exponential backoff + jitter, retry budget, circuit breaker**. Giải thích **metastable failure** và chặn nó bằng **load shedding**.

---

## 1. Chạy service: process model, probe, tắt máy

### 1.1. Đóng gói

Một Dockerfile multi-stage cho `invoice-api`. Stage build cài dependency vào virtualenv, stage chạy chỉ chép virtualenv và code:

```dockerfile
FROM python:3.13-slim AS build
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project      # lớp dependency: cache được khi chỉ đổi code
COPY app/ app/
RUN uv sync --frozen --no-dev

FROM python:3.13-slim
WORKDIR /app
RUN useradd --uid 10001 --no-create-home app
COPY --from=build /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--loop", "uvloop", "--http", "httptools", "--timeout-graceful-shutdown", "20"]
```

Ba điểm đáng chú ý:

- Chạy bằng **user không phải root**.
- `CMD` dạng **exec** (mảng JSON) để uvicorn là PID 1 và nhận được `SIGTERM`. Với dạng shell, tín hiệu dừng ở `/bin/sh`.
- Chọn uvloop + httptools một cách tường minh. Module 09 đã đo: bỏ uvloop mà chạy `--workers` có thể cộng thêm 40 ms vì Nagle.

### 1.2. Một tiến trình mỗi pod, hay nhiều worker?

| | 1 tiến trình / pod, scale bằng số pod | N worker / pod (`--workers N` hoặc gunicorn) |
|---|---|---|
| Scale | Kubernetes HPA, đơn vị nhỏ | thô, theo pod lớn |
| Health check | probe phản ánh đúng tiến trình duy nhất | probe chỉ tới được một worker bất kỳ; một worker treo có thể không bị phát hiện |
| Tài nguyên | `requests/limits` CPU ≈ 1 core rõ ràng | phải đặt limit đủ cho N tiến trình |
| Bộ nhớ | mỗi pod một bản app | chia sẻ copy-on-write (ít khi đáng kể với Python) |
| Pool DB | `pool_size` mỗi pod (Module 10) | mỗi worker một pool, tổng = N × pool |

Trên Kubernetes, mình khuyên **một tiến trình Uvicorn mỗi container**. Nền tảng đã làm việc của process manager: khởi động lại, đếm số bản, cân bằng tải. Giữ `--workers` cho máy ảo hoặc máy chủ không có orchestrator.

<!-- placeholder-process -->

<!-- fig:process -->
<figure markdown="span">
  ![Hai process model: một Uvicorn mỗi pod (Kubernetes) và nhiều worker mỗi máy](assets/figures/13/process.light.svg#only-light){ loading=lazy }
  ![Hai process model: một Uvicorn mỗi pod (Kubernetes) và nhiều worker mỗi máy](assets/figures/13/process.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 13.1 — Hai process model: một Uvicorn mỗi pod (Kubernetes) và nhiều worker mỗi máy.</figcaption>
</figure>
<!-- /fig -->

### 1.3. Ba loại probe

| Probe | Câu hỏi | Thất bại thì | Endpoint cho `invoice-api` |
|---|---|---|---|
| **startup** | đã khởi động xong chưa? (migration check, nạp cache) | chưa chạy hai probe kia; quá ngưỡng thì khởi động lại | `/health/startup` |
| **liveness** | tiến trình còn sống và **tự hồi phục được không**? | **khởi động lại** container | `/health/live`: chỉ kiểm event loop còn phản hồi |
| **readiness** | có nên **nhận traffic** lúc này không? | **rút khỏi** load balancer (không khởi động lại) | `/health/ready`: kiểm pool DB, Redis, cờ "đang tắt" |

<!-- placeholder-probes -->

<!-- fig:probes -->
<figure markdown="span">
  ![Ba loại probe trả lời ba câu hỏi khác nhau; phụ thuộc bên ngoài chỉ thuộc readiness](assets/figures/13/probes.light.svg#only-light){ loading=lazy }
  ![Ba loại probe trả lời ba câu hỏi khác nhau; phụ thuộc bên ngoài chỉ thuộc readiness](assets/figures/13/probes.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 13.2 — Ba loại probe trả lời ba câu hỏi khác nhau; phụ thuộc bên ngoài chỉ thuộc readiness.</figcaption>
</figure>
<!-- /fig -->

Sai lầm phổ biến nhất là **liveness kiểm database**. Khi DB chậm 10 giây, mọi pod cùng fail liveness, Kubernetes khởi động lại **tất cả**, rồi 20 pod cùng mở pool kết nối tới DB vốn đang chậm. Sự cố nhỏ thành sự cố lớn. Phụ thuộc bên ngoài chỉ thuộc về **readiness**. Pod không sẵn sàng thì bị rút khỏi load balancer, chứ không bị giết.

### 1.4. Graceful shutdown: thí nghiệm

Rolling deploy, autoscale xuống, node bị thay: mọi trường hợp đều bắt đầu bằng `SIGTERM`. Thí nghiệm `p1` gửi 10 request dài 2 giây, gửi `SIGTERM` ở giây 0,5, rồi gửi thêm 10 request **mới** ở giây 0,8:

| Cấu hình uvicorn | 10 request đang chạy | 10 request đến sau SIGTERM | Tiến trình thoát sau |
|---|---|---|---|
| mặc định | **10/10 xong** | **0/10**: `ConnectionRefusedError` | 1,62 s |
| `--timeout-graceful-shutdown 1` | **0/10**: bị cắt sau 1 s | 0/10: `ConnectionRefusedError` | 1,20 s |

Uvicorn làm phần của nó đúng: ngừng nhận kết nối mới và chờ request đang chạy xong. Mặc định nó **chờ vô hạn**, nên `--timeout-graceful-shutdown` phải nhỏ hơn `terminationGracePeriodSeconds` của Kubernetes (mặc định 30 s). Nhưng **request mới đến sau SIGTERM vẫn bị từ chối**. Trên Kubernetes, việc rút pod khỏi Service (cập nhật EndpointSlice, kube-proxy, ingress) diễn ra **song song và bất đồng bộ** với việc gửi SIGTERM. Trong vài giây đó, traffic vẫn được gửi tới một tiến trình đã đóng socket.

<!-- placeholder-shutdown -->

<!-- fig:shutdown -->
<figure markdown="span">
  ![Trình tự graceful shutdown trên Kubernetes và số đo thật của uvicorn khi nhận SIGTERM](assets/figures/13/shutdown.light.svg#only-light){ loading=lazy }
  ![Trình tự graceful shutdown trên Kubernetes và số đo thật của uvicorn khi nhận SIGTERM](assets/figures/13/shutdown.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 13.3 — Trình tự graceful shutdown trên Kubernetes và số đo thật của uvicorn khi nhận SIGTERM.</figcaption>
</figure>
<!-- /fig -->

Cách xử lý chuẩn:

```yaml
spec:
  terminationGracePeriodSeconds: 30
  containers:
    - name: invoice-api
      lifecycle:
        preStop:
          exec: {command: ["sleep", "8"]}      # chờ LB/ingress rút pod trước khi uvicorn nhận SIGTERM
      readinessProbe:
        httpGet: {path: /health/ready, port: 8000}
        periodSeconds: 2
        failureThreshold: 1
      livenessProbe:
        httpGet: {path: /health/live, port: 8000}
        periodSeconds: 10
        failureThreshold: 3
      startupProbe:
        httpGet: {path: /health/startup, port: 8000}
        periodSeconds: 2
        failureThreshold: 30                     # tối đa 60 s để khởi động
```

Trình tự khi đó: `preStop` (8 s, pod được rút khỏi mọi load balancer trong lúc này) → `SIGTERM` → uvicorn chờ request dở dang tối đa 20 s → lifespan shutdown đóng pool DB và flush telemetry → thoát. Tổng 28 s, vẫn dưới 30 s.

---

## 2. Quan sát: log, metric, trace

### 2.1. Ba trụ và sợi chỉ nối chúng

| | Trả lời | Dạng | Chi phí lưu trữ |
|---|---|---|---|
| **Metric** | hệ thống có khỏe không? bao nhiêu, nhanh cỡ nào? | số tổng hợp theo thời gian (counter, histogram) | rẻ, không phụ thuộc lưu lượng |
| **Trace** | request **này** đi qua đâu, chậm ở đâu? | cây span có thời gian | theo lưu lượng, thường **lấy mẫu** |
| **Log** | chuyện gì đã xảy ra, chi tiết? | sự kiện rời rạc, có cấu trúc (JSON) | theo lưu lượng, đắt nhất |

Giá trị nằm ở chỗ **nối** được chúng: metric báo p99 tăng → exemplar dẫn tới một trace chậm → `trace_id` trong trace dẫn tới đúng các dòng log của request đó. Muốn vậy, mọi dòng log phải mang `trace_id` (hoặc `request_id`) và `tenant_id`.

<!-- placeholder-pillars -->

<!-- fig:pillars -->
<figure markdown="span">
  ![Ba trụ quan sát và cách nối chúng: exemplar dẫn tới trace, traceid dẫn tới log](assets/figures/13/pillars.light.svg#only-light){ loading=lazy }
  ![Ba trụ quan sát và cách nối chúng: exemplar dẫn tới trace, traceid dẫn tới log](assets/figures/13/pillars.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 13.4 — Ba trụ quan sát và cách nối chúng: exemplar dẫn tới trace, trace_id dẫn tới log.</figcaption>
</figure>
<!-- /fig -->

Mô hình trace hiện đại bắt nguồn từ **Dapper** của Google (Sigelman và cộng sự, 2010): mỗi request mang một trace ID truyền qua mọi dịch vụ, và mỗi đơn vị công việc là một span có cha. **OpenTelemetry** (hợp nhất OpenTracing và OpenCensus, thuộc CNCF) chuẩn hóa API, SDK, giao thức OTLP và **ngữ nghĩa thuộc tính** (`http.request.method`, `http.route`, `http.response.status_code`…), để mọi backend (Jaeger, Tempo, Honeycomb, Datadog…) hiểu như nhau. Trace ID truyền giữa các dịch vụ qua header **`traceparent`** theo chuẩn W3C Trace Context.

### 2.2. Telemetry tích hợp của FastAPI

FastAPI 0.143 có **OpenTelemetry tích hợp** (`fastapi.telemetry`). Nó tự bật khi có tracer/meter/logger provider được cấu hình (toàn cục, hoặc truyền vào `FastAPI(telemetry={...})`). Nó tạo:

- span server cho mỗi request, với `http.route` là **template** (`/v1/invoices/{invoice_id}`, không phải URL cụ thể, để metric không bùng nổ số chuỗi);
- **operation span** cho giải dependency, endpoint, serialization, background task;
- metric thời gian request;
- log cho lỗi validation và exception chưa xử lý.

```python
from fastapi import FastAPI
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

tp = TracerProvider(sampler=ParentBased(TraceIdRatioBased(0.05)))   # 5% trace gốc; theo quyết định của cha
tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))       # gửi theo lô, không chặn request

app = FastAPI(telemetry={
    "tracer_provider": tp,
    "operation_spans": False,                                        # tắt span con cho đường nóng (xem 2.3)
    "exclude": lambda scope: scope["path"].startswith("/health"),   # không trace probe
})
```

Starlette 1.x cũng có `starlette.middleware.opentelemetry.OpenTelemetryMiddleware` (đang ở mức thử nghiệm) cho app Starlette thuần.

### 2.3. Quan sát tốn bao nhiêu? Số đo

Thí nghiệm `p5`: cùng một `POST` hóa đơn 12 dòng, đo trong tiến trình (một core, lấy giá trị nhỏ nhất của 3 lần chạy; nhiễu giữa các lần chạy cỡ ±10%):

| Cấu hình | µs/request | Tăng thêm |
|---|---|---|
| không quan sát gì | 93 | — |
| + log JSON một dòng/request (ASGI middleware, stdlib `logging`) | 125 | +32 |
| + histogram Prometheus (ASGI middleware) | 98 | +5 |
| + OTel tích hợp của FastAPI, chỉ span server | 120 | +27 |
| + OTel tích hợp, **có operation span** (mặc định; 4 span/request) | 258 | **+165** |
| + như trên, **lấy mẫu 10%** | 195 | +102 |

<!-- placeholder-obs-cost -->

<!-- fig:obs-cost -->
<figure markdown="span">
  ![Số đo thật: chi phí mỗi request của log, metric và telemetry tích hợp của FastAPI](assets/figures/13/obs-cost.light.svg#only-light){ loading=lazy }
  ![Số đo thật: chi phí mỗi request của log, metric và telemetry tích hợp của FastAPI](assets/figures/13/obs-cost.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 13.5 — Số đo thật: chi phí mỗi request của log, metric và telemetry tích hợp của FastAPI.</figcaption>
</figure>
<!-- /fig -->

Bốn điều rút ra:

1. **Metric gần như miễn phí** (~5 µs): một lần cộng vào bucket. Hãy đo mọi thứ bằng metric trước.
2. **Một dòng log JSON tốn ~32 µs**, phần lớn là `json.dumps` và hệ thống `logging` của Python (lock, handler). Ở 500 req/s, đó là 1,6% một core, chấp nhận được. Nhưng 10 dòng log/request là 16%. Log có chủ đích, không log "cho chắc".
3. **Operation span đắt gấp ~6 lần span server**: mỗi request tạo 4 span thay vì 1, mỗi span có thuộc tính, thời điểm, context. Với đường nóng của `invoice-api` (ngân sách CPU ~0,5 ms/request, Module 09), +165 µs là +33%. Bật operation span khi cần chẩn đoán, hoặc cho các route chậm.
4. **Lấy mẫu không làm chi phí về 0**: lấy mẫu 10% vẫn tốn +102 µs. Span không được ghi vẫn phải được tạo (non-recording span), context vẫn phải truyền, và FastAPI vẫn chạy phần bọc của nó. Lấy mẫu giảm chi phí **xuất và lưu trữ** nhiều hơn chi phí **tạo span**.

### 2.4. Metric: RED, USE và histogram

Hai phương pháp chọn metric đáng nhớ:

- **RED** (Tom Wilkie, cho dịch vụ request/response): **R**ate (req/s), **E**rrors (tỉ lệ lỗi), **D**uration (phân phối latency) cho mỗi route.
- **USE** (Brendan Gregg, cho tài nguyên): **U**tilization, **S**aturation (độ dài hàng đợi), **E**rrors cho CPU, pool DB, threadpool, event loop.

Với `invoice-api`, những metric bão hòa đáng giá nhất là:

- số kết nối đang mượn và **thời gian chờ pool** (Module 10);
- số luồng threadpool đang bận (Module 09);
- **độ trễ của event loop**: đo bằng một task `sleep(0.1)` định kỳ, phần chênh với 0,1 s.

Đây là các tín hiệu báo trước, xuất hiện **trước khi** latency tăng.

### 2.5. Percentile: hai cái bẫy, số đo

Latency phải được đo bằng **phân phối**, không phải trung bình (Module 09: tail at scale). Nhưng percentile có hai bẫy khi tổng hợp (thí nghiệm `p4`, 4 pod, pod-d "nóng" vì noisy neighbor):

| Đại lượng | Giá trị |
|---|---|
| p99 từng pod | a: 92, b: 95, c: 92, **d: 366** ms |
| **trung bình các p99** (dashboard hay làm) | **161 ms** |
| **p99 thật** (gộp mọi mẫu) | **198 ms** |
| `histogram_quantile(0.99)` với bucket mặc định của client Prometheus | 232 ms |
| `histogram_quantile(0.99)` với bucket chỉnh quanh SLO (…150, 175, 200, 250, 300…) | 198 ms |

<!-- placeholder-percentiles -->

<!-- fig:percentiles -->
<figure markdown="span">
  ![Trung bình các p99 không phải p99; độ chính xác của histogramquantile phụ thuộc bucket](assets/figures/13/percentiles.light.svg#only-light){ loading=lazy }
  ![Trung bình các p99 không phải p99; độ chính xác của histogramquantile phụ thuộc bucket](assets/figures/13/percentiles.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 13.6 — Trung bình các p99 không phải p99; độ chính xác của histogram_quantile phụ thuộc bucket.</figcaption>
</figure>
<!-- /fig -->

1. **Không lấy trung bình percentile.** Trung bình các p99 không phải p99 của tổng thể, và ở đây nó thấp hơn 19%, đúng lúc có một pod gặp vấn đề. Percentile phải được tính từ **phân phối gộp**: gộp **histogram** (cộng các bucket qua mọi pod rồi mới tính quantile), không gộp con số đã tính.
2. **Độ chính xác do bucket quyết định.** `histogram_quantile` nội suy tuyến tính trong bucket chứa quantile. Bucket mặc định (…100, 250, 500…) quá thưa quanh 200 ms nên ước lượng lệch +17%. Đặt bucket **dày quanh ngưỡng SLO** (300 ms với `invoice-api`) để câu hỏi "bao nhiêu % request dưới 300 ms" có câu trả lời **chính xác**, không phải nội suy. Đó mới là câu hỏi SLO cần.

---

## 3. SLO và error budget

### 3.1. Định nghĩa

- **SLI** (indicator): một tỉ lệ đo được. Ví dụ: "tỉ lệ `POST /v1/invoices` trả 2xx/4xx (không phải 5xx) **và** trong 300 ms".
- **SLO** (objective): mục tiêu cho SLI trong một cửa sổ. Ví dụ: **99,9% trong 30 ngày**.
- **Error budget** $= 1 - \text{SLO}$: phần được phép hỏng. Hết budget thì ưu tiên độ tin cậy hơn tính năng mới.

Cho `invoice-api` (1,8 triệu request/ngày):

$$
\text{budget} = (1 - 0{,}999) \times 1{,}8 \times 10^6 \times 30 = 54.000 \text{ request hỏng / 30 ngày} \;\approx\; 43{,}2 \text{ phút sập hoàn toàn}
$$

### 3.2. Cảnh báo theo burn rate

**Burn rate** là tốc độ tiêu budget so với tốc độ "vừa hết đúng cuối cửa sổ". Burn rate $B$ duy trì trong thời gian $t$ tiêu một tỉ lệ $B \cdot t / T$ budget, với $T = 30$ ngày:

| Burn rate | Tiêu trong cửa sổ cảnh báo | Hết budget sau | Hành động (theo SRE Workbook) |
|---|---|---|---|
| 14,4 | 2% trong 1 giờ | 50 giờ | **gọi người trực** |
| 6 | 5% trong 6 giờ | 5 ngày | gọi người trực |
| 1 | 10% trong 3 ngày | 30 ngày | tạo ticket |

<!-- placeholder-slo -->

<!-- fig:slo -->
<figure markdown="span">
  ![Error budget còn lại theo thời gian với các burn rate dùng để cảnh báo](assets/figures/13/slo.light.svg#only-light){ loading=lazy }
  ![Error budget còn lại theo thời gian với các burn rate dùng để cảnh báo](assets/figures/13/slo.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 13.7 — Error budget còn lại theo thời gian với các burn rate dùng để cảnh báo.</figcaption>
</figure>
<!-- /fig -->

Chương *Alerting on SLOs* của **The Site Reliability Workbook** (Google, 2018) khuyên dùng **nhiều cửa sổ**: cảnh báo khi burn rate vượt ngưỡng ở **cả** cửa sổ dài (1 h, để chắc là thật) **và** cửa sổ ngắn (5 phút, để cảnh báo tự tắt nhanh khi đã hết). Cách này tốt hơn hẳn "p99 > 300 ms trong 5 phút", vốn ồn khi ít traffic và chậm khi có sự cố thật.

```promql
# tỉ lệ lỗi trong 1 h và 5 phút; cảnh báo khi cả hai > 14,4 × 0,001
(
  sum(rate(http_requests_total{route="/v1/invoices",status=~"5.."}[1h]))
  / sum(rate(http_requests_total{route="/v1/invoices"}[1h]))
) > (14.4 * 0.001)
and
(
  sum(rate(http_requests_total{route="/v1/invoices",status=~"5.."}[5m]))
  / sum(rate(http_requests_total{route="/v1/invoices"}[5m]))
) > (14.4 * 0.001)
```

---

## 4. Khi phụ thuộc thất bại: timeout, retry, backoff

### 4.1. Timeout ở mọi lời gọi ra ngoài

Mọi lời gọi qua mạng phải có timeout, và timeout của tầng trong phải **ngắn hơn** tầng ngoài. Ngân sách của `POST /v1/invoices`: p99 300 ms. Phân bổ: DB 100 ms/truy vấn (`statement_timeout` ở Postgres), pool 50 ms (`pool_timeout`), Redis 20 ms, tổng request 1 s ở proxy. Với `ai-gateway`, lời gọi LLM có timeout 45 s (p99 của LLM ~30 s), và **giới hạn tổng thời gian** cho cả chuỗi retry.

```python
import asyncio

async with asyncio.timeout(0.1):                    # Python 3.11+: hủy cả khối nếu quá 100 ms
    rate_ok = await limiter.check(tenant_id)
```

### 4.2. Retry: khi nào và bao nhiêu lần

Chỉ retry khi lỗi **tạm thời** (timeout, 503, 429, kết nối bị reset) **và** thao tác **idempotent**: GET, hoặc POST có `Idempotency-Key` (Module 10). Retry một POST không có idempotency key là cách tạo hóa đơn trùng.

### 4.3. Backoff và jitter: mô phỏng

Mô phỏng `p2` theo mô hình của Marc Brooker (*Exponential Backoff And Jitter*, AWS Architecture Blog, 2015). 100 client cùng gọi vào một tài nguyên chỉ phục vụ được 2 lần gọi mỗi khe 10 ms. Lần gọi thất bại thì retry theo chiến lược (base 10 ms, trần 2 s):

| Chiến lược | Tổng số lần gọi | Lần gọi/client | Một nửa xong sau | Tất cả xong sau |
|---|---|---|---|---|
| retry ngay (chờ 1 ms) | 24.600 | 246 | 0,25 s | 0,49 s |
| exponential, **không jitter** | 2.550 | 25,5 | 36,6 s | **84,6 s** |
| full jitter: `uniform(0, min(cap, base·2ⁿ))` | 646 | 6,5 | 0,26 s | 1,75 s |
| equal jitter | 628 | 6,3 | 0,38 s | 1,14 s |
| decorrelated jitter: `min(cap, uniform(base, prev·3))` | **594** | **5,9** | 0,25 s | **0,96 s** |

<!-- placeholder-backoff -->

<!-- fig:backoff -->
<figure markdown="span">
  ![Mô phỏng: tải tạo ra và thời gian hoàn thành của các chiến lược retry khi 100 client tranh một tài nguyên](assets/figures/13/backoff.light.svg#only-light){ loading=lazy }
  ![Mô phỏng: tải tạo ra và thời gian hoàn thành của các chiến lược retry khi 100 client tranh một tài nguyên](assets/figures/13/backoff.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 13.8 — Mô phỏng: tải tạo ra và thời gian hoàn thành của các chiến lược retry khi 100 client tranh một tài nguyên.</figcaption>
</figure>
<!-- /fig -->

- **Retry ngay** xong nhanh trong mô hình lý tưởng này, nhưng bằng cách bắn **246 lần gọi mỗi client**, tức tải gấp 40 lần. Ngoài đời, chính lượng tải đó làm tài nguyên chậm thêm (mục 4.4).
- **Exponential không jitter là tệ nhất**: 100 client thất bại cùng lúc thì chờ **cùng một khoảng** và retry **cùng lúc**, lần nào cũng va nhau. Backoff chỉ dời cuộc va chạm ra xa hơn: 84 giây để xong.
- **Jitter phá sự đồng bộ**: số lần gọi giảm 4 lần so với không jitter, thời gian giảm ~80 lần.

```python
import random


def backoff(attempt: int, prev: float, base: float = 0.05, cap: float = 5.0) -> float:
    return min(cap, random.uniform(base, prev * 3))      # decorrelated jitter
```

### 4.4. Metastable failure: khi retry giữ hệ thống ở trạng thái hỏng

Bronson và cộng sự (**HotOS 2021**, *Metastable Failures in Distributed Systems*) gọi tên một loại sự cố quen thuộc. Một **tác nhân kích hoạt** tạm thời (DB chậm, mất một node, đợt tải đột biến) đẩy hệ thống vào trạng thái quá tải. Sau đó một **cơ chế tự duy trì**, thường là retry, giữ nó ở trạng thái đó **kể cả khi tác nhân đã biến mất**. Huang và cộng sự (**OSDI 2022**, *Metastable Failures in the Wild*) phân tích các sự cố thật kiểu này ở nhiều tổ chức, trong đó có các nhà cung cấp cloud lớn. Họ thấy **retry** là một trong những cơ chế duy trì phổ biến nhất.

Mô phỏng `p3` dùng một server FIFO năng lực 100 req/s và khách đến 80 req/s. Client hết kiên nhẫn sau 1 s; server **không biết** điều đó và vẫn xử lý request đã bị bỏ. Từ giây 30 đến giây 40, năng lực tụt còn 40 req/s (tác nhân kích hoạt), rồi trở lại 100:

| Chính sách của client / server | Goodput trước | Trong sự cố | Hồi phục sau khi sự cố hết | Goodput giây 80–120 | Tải gửi tới sau sự cố |
|---|---|---|---|---|---|
| không retry | 80/s | 10/s | 17 s | 77/s | 77/s |
| **retry tối đa 3 lần, không chờ** | 80/s | 10/s | **không bao giờ** (trong 80 s quan sát) | **0/s** | **308/s** |
| retry có backoff + jitter + **retry budget 10%** | 80/s | 10/s | 40 s | 79/s | 77/s |
| không retry + **load shedding** (từ chối khi chờ dự kiến > timeout) | 80/s | **21/s** | **~1 s** | 77/s | 77/s |

<!-- placeholder-metastable -->

<!-- fig:metastable -->
<figure markdown="span">
  ![Mô phỏng metastable failure: sau khi sự cố hết, retry không chờ giữ goodput bằng 0; backoff có budget và load shedding thì hồi phục](assets/figures/13/metastable.light.svg#only-light){ loading=lazy }
  ![Mô phỏng metastable failure: sau khi sự cố hết, retry không chờ giữ goodput bằng 0; backoff có budget và load shedding thì hồi phục](assets/figures/13/metastable.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 13.9 — Mô phỏng metastable failure: sau khi sự cố hết, retry không chờ giữ goodput bằng 0; backoff có budget và load shedding thì hồi phục.</figcaption>
</figure>
<!-- /fig -->

Cơ chế của dòng thứ hai: khi hàng đợi dài hơn 1 giây, mọi request đều timeout phía client. Mỗi request được gửi lại tối đa 4 lần, nên tải gửi tới gấp gần 4 lần (308/s), vượt xa năng lực 100/s. Server vẫn làm việc, nhưng làm cho những request **đã bị bỏ**. Hàng đợi không bao giờ ngắn lại, và goodput bằng 0 vĩnh viễn, dù "nguyên nhân" đã hết từ lâu. Khởi động lại server cũng không cứu được, vì hàng đợi sẽ đầy lại ngay. Phải cắt vòng khuếch đại.

Ngay cả khi **không retry**, hệ thống vẫn mất 17 giây để hồi phục. Lý do là server phải xử lý hết lượng request tồn đọng mà client đã bỏ: công vô ích. Có retry budget, hệ thống vẫn hồi phục, nhưng chậm hơn (40 s), vì retry vẫn cộng thêm tải trong lúc hàng đợi rút. Chỉ load shedding hồi phục gần như tức thì, vì hàng đợi không bao giờ được phép dài hơn mức client còn chờ.

Các biện pháp, theo thứ tự hiệu quả:

1. **Retry budget**: tổng số retry không vượt quá ~10% số request gốc (token bucket phía client; gRPC và Envoy đều có). Đây là cách chặn khuếch đại trực tiếp nhất.
2. **Backoff có jitter** (mục 4.3), và **chỉ retry ở một tầng**. Ba tầng, mỗi tầng retry 3 lần, là $4^3 = 64$ lần gọi ở tầng dưới cùng.
3. **Load shedding** ở server: từ chối sớm (503 + `Retry-After`) những request **chắc chắn không kịp**, để năng lực dành cho request còn cứu được.
4. **Circuit breaker** (Nygard, *Release It!*): sau N lỗi liên tiếp tới một phụ thuộc thì "ngắt mạch", trả lỗi ngay trong một khoảng thời gian, rồi thử lại từng chút (half-open). Nó bảo vệ cả phụ thuộc (cho nó thời gian hồi phục) lẫn chính mình (không giữ luồng và kết nối để chờ thứ chắc chắn hỏng).

### 4.5. Load shedding: thí nghiệm thật

Thí nghiệm `p6`: uvicorn thật, một tiến trình, endpoint tốn ~4 ms CPU (năng lực ~200 req/s). Tải open-loop Poisson trong 20 giây, client timeout 1 s:

| Cấu hình | Tải | Goodput | 503 (từ chối nhanh) | **Timeout** (chờ 1 s rồi hỏng) | p50 / p99 của request thành công |
|---|---|---|---|---|---|
| không giới hạn | 150/s | 149/s | 0 | 0 | 11 / 63 ms |
| không giới hạn | **300/s** | 201/s | 0 | **1.956** | 274 / 346 ms |
| `uvicorn --limit-concurrency 20` | 300/s | **31/s** | 5.360 | 0 | 25 / 218 ms |
| **ASGI middleware: tối đa 20 request in-flight** | 300/s | **220/s** | 1.583 | **0** | **133 / 182 ms** |

<!-- placeholder-shedding -->

<!-- fig:shedding -->
<figure markdown="span">
  ![Số đo thật: load shedding dưới tải 1,5 lần năng lực — không giới hạn, --limit-concurrency của uvicorn, và giới hạn in-flight ở tầng ứng dụng](assets/figures/13/shedding.light.svg#only-light){ loading=lazy }
  ![Số đo thật: load shedding dưới tải 1,5 lần năng lực — không giới hạn, --limit-concurrency của uvicorn, và giới hạn in-flight ở tầng ứng dụng](assets/figures/13/shedding.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 13.10 — Số đo thật: load shedding dưới tải 1,5 lần năng lực — không giới hạn, --limit-concurrency của uvicorn, và giới hạn in-flight ở tầng ứng dụng.</figcaption>
</figure>
<!-- /fig -->

- **Không giới hạn**: một phần ba request chờ đúng 1 giây rồi thất bại. Đó là trải nghiệm tệ nhất có thể, và client sẽ retry. Server còn tốn CPU cho những request mà client đã bỏ.
- **`--limit-concurrency` của uvicorn là cái bẫy**: nó đếm **kết nối và task**, không chỉ request đang xử lý. Client (hoặc load balancer) giữ nhiều kết nối keep-alive rảnh, các kết nối đó chiếm hết hạn mức, nên server từ chối gần như mọi request: goodput còn 31/s. Nó hợp để bảo vệ khỏi cạn file descriptor, không hợp làm load shedding.
- **Giới hạn số request in-flight ở tầng ứng dụng** cho goodput cao nhất (220/s), không timeout nào, latency của request thành công thấp nhất. Request bị từ chối nhận 503 ngay lập tức, kèm `Retry-After`. Đó là tín hiệu tốt hơn nhiều so với im lặng 1 giây.

Middleware này chỉ ~20 dòng (thuần ASGI, Module 07). Đặt ngưỡng theo định luật Little: năng lực × latency mục tiêu, ví dụ 200 req/s × 0,1 s = 20.

---

## 5. Case Mekong Cloud: cấu hình vận hành của hai dịch vụ

| Hạng mục | `invoice-api` | `ai-gateway` |
|---|---|---|
| Process model | 1 Uvicorn/pod, 1 vCPU; 4 pod (min), HPA tới 20 theo CPU 60% | 1 Uvicorn/pod; 2 pod; scale theo số SSE đang mở |
| Probe | readiness: pool DB + Redis + cờ tắt; liveness: event loop | readiness: thêm hạn mức LLM còn lại |
| Shutdown | preStop 8 s, `--timeout-graceful-shutdown 20` | preStop 8 s, gửi sự kiện SSE `retry` cho client rồi đóng; grace 60 s |
| Telemetry | span server + metric, operation span tắt; lấy mẫu 5%, giữ 100% trace lỗi/chậm ở collector (tail sampling) | operation span bật (ít request, mỗi request dài); span cho từng lần gọi LLM, kèm token in/out |
| SLI/SLO | 99,9% `POST` không 5xx **và** < 300 ms, 30 ngày | 99% draft sẵn sàng < 60 s sau webhook |
| Cảnh báo | burn rate 14,4 (1 h & 5 m), 6 (6 h & 30 m) | burn rate + chi phí LLM theo giờ |
| Retry | không retry phía server; client POS retry có jitter + `Idempotency-Key` | retry LLM tối đa 2 lần, decorrelated jitter, retry budget 10%, circuit breaker theo provider |
| Load shedding | in-flight ≤ 20/pod → 503 + `Retry-After: 1` | giới hạn lượt chạy đồng thời theo tenant |

---

## Lỗi thường gặp & cách xử lý

| Triệu chứng | Nguyên nhân gốc | Cách xử lý |
|---|---|---|
| Mỗi lần deploy có vài chục lỗi 502/connection refused | pod nhận SIGTERM trước khi được rút khỏi LB | `preStop: sleep`; readiness fail khi bắt đầu tắt |
| Deploy treo tới 30 s rồi pod bị SIGKILL | `--timeout-graceful-shutdown` không đặt; request dài/SSE | đặt timeout < grace period; báo client SSE kết nối lại |
| DB chậm → mọi pod restart cùng lúc | liveness kiểm DB | phụ thuộc ngoài chỉ ở readiness |
| Tín hiệu không tới uvicorn | `CMD` dạng shell, PID 1 là `sh` | `CMD` dạng exec |
| Dashboard p99 "ổn" khi có pod tệ | trung bình các percentile | gộp histogram rồi mới tính quantile |
| p99 nhảy bậc, không mượt | bucket histogram thưa quanh vùng quan tâm | bucket dày quanh ngưỡng SLO |
| CPU tăng ~30% sau khi bật tracing | operation span trên đường nóng | tắt `operation_spans` cho route nóng; lấy mẫu; exclude probe |
| Cảnh báo réo cả đêm khi ít traffic | ngưỡng tĩnh trên latency/lỗi | cảnh báo theo burn rate nhiều cửa sổ |
| Sự cố nhỏ thành sập kéo dài, khởi động lại không đỡ | retry khuếch đại (metastable) | retry budget, backoff + jitter, retry một tầng, load shedding |
| Retry tạo dữ liệu trùng | retry thao tác không idempotent | chỉ retry GET hoặc POST có `Idempotency-Key` |
| `--limit-concurrency` từ chối gần hết request | đếm cả kết nối keep-alive rảnh | giới hạn request in-flight ở tầng ứng dụng |
| Log chiếm nhiều CPU hơn xử lý request | log nhiều dòng/request, định dạng tốn kém | một dòng access log có cấu trúc; log mức DEBUG tắt ở production |

## Tóm tắt (cheat-sheet)

- **Container**: multi-stage, user không phải root, `CMD` dạng exec, uvloop + httptools; **1 Uvicorn/pod** trên Kubernetes.
- **Probe**: startup (khởi động), liveness (chỉ bản thân tiến trình), readiness (phụ thuộc ngoài + đang tắt). Không đưa DB vào liveness.
- **Shutdown**: preStop sleep → SIGTERM → chờ request dở dang (`--timeout-graceful-shutdown` < grace period) → lifespan dọn dẹp.
- **Quan sát**: metric ~5 µs, log JSON ~32 µs/dòng, span server ~27 µs, operation span +165 µs. Gắn `trace_id` + `tenant_id` vào log. RED cho route, USE cho pool/threadpool/event loop.
- **Percentile**: gộp histogram, không lấy trung bình p99; bucket dày quanh ngưỡng SLO.
- **SLO**: 99,9%/30 ngày ⇒ 54.000 request hỏng. Cảnh báo burn rate 14,4 (1 h + 5 m) và 6 (6 h + 30 m).
- **Lỗi**: timeout mọi lời gọi; retry chỉ khi tạm thời + idempotent; decorrelated jitter; retry budget 10%; retry một tầng; circuit breaker; load shedding = in-flight ≤ năng lực × latency mục tiêu.

## Câu hỏi tự kiểm tra / phỏng vấn

**1.** Vì sao không nên kiểm kết nối database trong liveness probe?

<details markdown="1">
<summary>Đáp án</summary>

Liveness thất bại thì Kubernetes **khởi động lại** container. Khi DB chậm hoặc tạm sập, mọi pod cùng fail liveness và bị khởi động lại đồng loạt. Khởi động lại không chữa được DB, lại mất cache, mất request đang chạy, và tạo một đợt mở kết nối dồn dập vào DB đang yếu. Phụ thuộc bên ngoài thuộc về readiness: pod tạm rút khỏi load balancer và tự quay lại khi DB khỏe.

</details>

**2.** Uvicorn đã chờ request đang chạy xong khi nhận SIGTERM. Vì sao rolling deploy vẫn có lỗi connection refused, và `preStop: sleep 8` giải quyết thế nào?

<details markdown="1">
<summary>Đáp án</summary>

Khi xóa pod, Kubernetes **đồng thời** gửi SIGTERM và cập nhật EndpointSlice. kube-proxy, ingress và load balancer cần vài giây để thấy thay đổi. Trong vài giây đó, traffic vẫn tới pod, nhưng uvicorn đã đóng socket lắng nghe ngay khi nhận SIGTERM, nên có connection refused (thí nghiệm `p1`: 10/10 request mới bị từ chối). `preStop` chạy **trước** SIGTERM. Trong 8 giây sleep, pod vẫn phục vụ bình thường trong khi các load balancer rút nó ra. Khi SIGTERM tới, đã không còn traffic mới.

</details>

**3.** Bật OTel tích hợp của FastAPI làm request chậm thêm 165 µs. Liệt kê ba cách giảm chi phí và nói rõ cách nào **không** hiệu quả như mong đợi.

<details markdown="1">
<summary>Đáp án</summary>

(1) Tắt `operation_spans` cho service nóng: chỉ còn span server, ~+27 µs. (2) `exclude` cho `/health` và các route không cần trace. (3) Dùng `BatchSpanProcessor` (không dùng Simple) để xuất span không chặn request. **Lấy mẫu** ít hiệu quả hơn mong đợi: lấy mẫu 10% vẫn tốn +102 µs, vì span vẫn được tạo (non-recording) và context vẫn được truyền. Lấy mẫu chủ yếu giảm chi phí xuất và lưu trữ.

</details>

**4.** Bốn pod có p99 lần lượt 92, 95, 92, 366 ms. Dashboard hiển thị "p99 = 161 ms". Sai ở đâu, và p99 thật là bao nhiêu?

<details markdown="1">
<summary>Đáp án</summary>

161 là trung bình các p99. Percentile không cộng hoặc trung bình được. p99 của tổng thể phụ thuộc vào cả phân phối và **lượng traffic** của từng pod. Gộp mọi mẫu (hoặc cộng histogram của các pod) thì p99 thật là ~198 ms, cao hơn 23%. Dashboard đúng: `histogram_quantile(0.99, sum by (le) (rate(..._bucket[5m])))`.

</details>

**5.** SLO 99,9% trong 30 ngày. Một sự cố làm tỉ lệ lỗi 1,44% trong 1 giờ. Đã tiêu bao nhiêu budget? Có nên gọi người trực không?

<details markdown="1">
<summary>Đáp án</summary>

Burn rate $= 0{,}0144 / 0{,}001 = 14{,}4$. Trong 1 giờ nó tiêu $14{,}4 \times 1 / 720 = 2\%$ budget. Nếu kéo dài, budget hết sau 50 giờ. Theo SRE Workbook, burn rate ≥ 14,4 ở cửa sổ 1 h (và vẫn cao ở cửa sổ 5 phút) là mức **gọi người trực**.

</details>

**6.** Vì sao exponential backoff **không jitter** cho kết quả tệ hơn cả retry ngay lập tức, xét theo thời gian hoàn thành?

<details markdown="1">
<summary>Đáp án</summary>

Các client thất bại cùng lúc sẽ tính ra **cùng một** thời gian chờ $\text{base} \cdot 2^n$ và retry cùng lúc, nên lại va nhau. Mỗi vòng, chỉ vài client thành công, số còn lại chờ lâu gấp đôi rồi lại va nhau. Thời gian hoàn thành tăng theo cấp số nhân (84 s trong mô phỏng). Retry ngay thì liên tục thử nên tận dụng mọi khe trống, nhưng trả giá bằng tải gấp nhiều lần. Jitter giải quyết cả hai: phân tán các lần retry để không va nhau, và vẫn giảm tải.

</details>

**7.** Giải thích metastable failure bằng mô phỏng `p3`. Vì sao khởi động lại server không giải quyết được?

<details markdown="1">
<summary>Đáp án</summary>

Tác nhân (năng lực tụt 40 req/s trong 10 s) làm hàng đợi dài quá 1 s. Mọi request timeout phía client, client retry, nên tải gửi tới tăng gần 4 lần (308/s) và vượt năng lực 100/s **ngay cả khi năng lực đã phục hồi**. Server tốn sức xử lý request đã bị bỏ, hàng đợi không ngắn lại, goodput = 0. Khởi động lại làm rỗng hàng đợi, nhưng 308 req/s vẫn đang đổ tới nên hàng đợi đầy lại trong vài giây. Phải giảm tải khuếch đại: retry budget, backoff, hoặc load shedding.

</details>

**8.** Vì sao `uvicorn --limit-concurrency 20` cho goodput 31/s trong khi middleware giới hạn 20 request in-flight cho 220/s?

<details markdown="1">
<summary>Đáp án</summary>

`--limit-concurrency` đếm **kết nối và task** đang mở. Client và load balancer giữ nhiều kết nối keep-alive **rảnh**, và chúng chiếm hạn mức, nên server trả 503 cho phần lớn request dù CPU còn rảnh. Middleware đếm đúng thứ cần giới hạn: request **đang được xử lý**.

</details>

**9.** Ba tầng gọi nhau (gateway → `ai-gateway` → LLM provider), mỗi tầng retry 3 lần. Trong trường hợp xấu nhất, một request của người dùng tạo bao nhiêu lời gọi tới LLM? Sửa thế nào?

<details markdown="1">
<summary>Đáp án</summary>

Mỗi tầng gọi tối đa 4 lần (1 + 3 retry), nên tầng dưới cùng nhận $4^3 = 64$ lời gọi. Sửa: chỉ retry ở **một** tầng, thường là tầng gần phụ thuộc nhất (`ai-gateway` → LLM). Các tầng trên truyền lỗi lên, hoặc retry với retry budget rất nhỏ. Đặt **deadline** tổng cho request và truyền nó xuống (header `grpc-timeout` hoặc tự định nghĩa), để tầng dưới không retry khi tầng trên đã hết kiên nhẫn.

</details>

**10.** Đặt ngưỡng load shedding (số request in-flight) cho một pod có năng lực 200 req/s và mục tiêu latency 100 ms. Giải thích.

<details markdown="1">
<summary>Đáp án</summary>

Theo định luật Little, $L = \lambda W = 200 \times 0{,}1 = 20$ request in-flight là mức tương ứng với việc chạy hết năng lực mà latency trung bình vẫn ở 100 ms. Cho phép nhiều hơn thì latency tăng mà thông lượng không tăng (server đã bão hòa). Request thứ 21 trở đi nên nhận 503 ngay để client retry ở pod khác hoặc sau `Retry-After`.

</details>

## Bài tập thực hành

1. **Graceful shutdown trên kind.** Deploy `invoice-api` lên một cluster kind, chạy tải liên tục 100 req/s, rồi `kubectl rollout restart`. Đếm số lỗi khi không có `preStop` và khi có `preStop: sleep 8`.
2. **Dashboard RED.** Viết một ASGI middleware xuất `http_server_request_duration_seconds` với bucket chỉnh quanh 300 ms (nhãn `route` là template), và một truy vấn PromQL tính tỉ lệ request < 300 ms trong 30 ngày.
3. **Retry budget.** Cài token bucket phía client cho `httpx`: mỗi request gốc +0,1 token, mỗi retry −1 token. Chạy lại mô phỏng `p3` với client này và so goodput sau sự cố.
4. **Circuit breaker.** Cài circuit breaker ba trạng thái (closed / open / half-open) cho lời gọi LLM của `ai-gateway`. Viết test bằng `dependency_overrides` với một provider giả thất bại theo kịch bản.

## Tài liệu tham khảo

- B. H. Sigelman, L. A. Barroso, M. Burrows, P. Stephenson, M. Plakal, D. Beaver, S. Jaspan, C. Shanbhag. *Dapper, a Large-Scale Distributed Systems Tracing Infrastructure*. Google Technical Report dapper-2010-1, 2010.
- N. Bronson, A. Aghayev, A. Charapko, T. Zhu. *Metastable Failures in Distributed Systems*. **HotOS 2021**.
- L. Huang, M. Magnusson, A. B. Muralikrishna, S. Estyak, R. Isaacs, A. Aghayev, T. Zhu, A. Charapko. *Metastable Failures in the Wild*. **OSDI 2022**.
- J. Dean, L. A. Barroso. *The Tail at Scale*. **Communications of the ACM** 56(2), 2013.
- M. Brooker. *Exponential Backoff And Jitter*. AWS Architecture Blog, 2015. [aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)
- B. Beyer, C. Jones, J. Petoff, N. R. Murphy (eds.). *Site Reliability Engineering*. O'Reilly, 2016. [sre.google/sre-book](https://sre.google/sre-book/table-of-contents/)
- B. Beyer, N. R. Murphy, D. K. Rensin, K. Kawahara, S. Thorne (eds.). *The Site Reliability Workbook* — chương *Alerting on SLOs*. O'Reilly, 2018. [sre.google/workbook/alerting-on-slos](https://sre.google/workbook/alerting-on-slos/)
- M. T. Nygard. *Release It! Design and Deploy Production-Ready Software*, 2nd ed. Pragmatic Bookshelf, 2018 (circuit breaker, bulkhead).
- B. Gregg. *The USE Method*. [brendangregg.com/usemethod.html](https://www.brendangregg.com/usemethod.html)
- T. Wilkie. *The RED Method: How to Instrument Your Services*. Grafana Labs, 2018.
- W3C. *Trace Context* (Recommendation). [w3.org/TR/trace-context](https://www.w3.org/TR/trace-context/)
- OpenTelemetry: [Specification](https://opentelemetry.io/docs/specs/otel/), [HTTP semantic conventions](https://opentelemetry.io/docs/specs/semconv/http/).
- Prometheus: [Histograms and summaries](https://prometheus.io/docs/practices/histograms/).
- Kubernetes: [Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/), [Pod Lifecycle — Termination of Pods](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination).
- Uvicorn: [Settings](https://www.uvicorn.org/settings/) (`--timeout-graceful-shutdown`, `--limit-concurrency`).
