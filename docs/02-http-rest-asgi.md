# Module 02 — HTTP, REST & ASGI: nền móng của một web API

> Thời lượng: ~50 phút · Mức độ: Trung bình · Tiên quyết: Module 00, kiến thức mạng máy tính cơ bản

FastAPI giấu đi rất nhiều thứ: bạn viết một hàm Python, và bằng cách nào đó nó trở thành một endpoint nhận hàng trăm request mỗi giây. Module này mở lớp vỏ đó ra theo chiều từ dưới lên: **ngữ nghĩa HTTP** (cái mà client và proxy trên đường đi tin vào), **REST** (một phong cách kiến trúc, không phải một giao thức), **ASGI** (hợp đồng giữa server và framework Python), **event loop** (cơ chế cho phép một tiến trình phục vụ hàng nghìn kết nối) và **GIL** (lý do Python cần nhiều tiến trình cho việc nặng CPU). Mọi quyết định về status code, idempotency, `async def` hay số worker ở các module sau đều dựa vào nền này.

## Mục tiêu học tập

Sau module này, bạn có thể:

1. Phân loại các method HTTP theo **safe / idempotent / cacheable** (RFC 9110) và chọn status code đúng cho từng tình huống của `invoice-api`.
2. Thiết kế **idempotency** cho một API tạo hóa đơn và ước lượng số hóa đơn trùng nếu thiếu nó.
3. Nêu các ràng buộc của **REST** (Fielding 2000), phân biệt "RESTful" thực sự và "HTTP + JSON", và thiết kế tài nguyên, phân trang, lỗi theo RFC 9457.
4. Viết một **ứng dụng ASGI thuần** không cần framework, giải thích `scope`, `receive`, `send` và lifespan.
5. Mô tả cách **event loop** của asyncio vận hành (selector, hàng đợi ready, timer) và vì sao một lời gọi chặn làm đứng toàn bộ tiến trình.
6. Giải thích **GIL**, tác động của nó lên code CPU-bound đa luồng, và trạng thái **free-threading** trong Python 3.14.
7. Lần theo một request `POST /v1/invoices` từ socket TCP đến hàm handler và ngược lại.

---

## 1. Ngữ nghĩa HTTP

### 1.1. Vấn đề

HTTP không chỉ là "cách gửi JSON". Giữa máy POS và `invoice-api` có Wi-Fi chập chờn, load balancer, có thể có CDN và proxy doanh nghiệp. Mọi thành phần đó **tin vào ngữ nghĩa** của method và status code: proxy có thể tự gửi lại một request `GET` khi mất kết nối, nhưng không được gửi lại `POST`; cache có thể giữ response `200` của `GET`. Dùng sai ngữ nghĩa là tạo ra lỗi mà code của bạn không hề thấy.

### 1.2. Tính chất của method (RFC 9110, 2022)

- **Safe**: client không yêu cầu thay đổi trạng thái server (đọc thuần túy). Crawler, prefetch của trình duyệt được phép gọi tùy ý.
- **Idempotent**: gửi $n \ge 1$ lần giống hệt gửi 1 lần, xét về **trạng thái server mà client dự định**. Hình thức: nếu $f$ là tác động của request lên trạng thái $s$ thì $f(f(s)) = f(s)$.
- **Cacheable**: response có thể được lưu và dùng lại.

| Method | Safe | Idempotent | Dùng trong `invoice-api` |
|---|---|---|---|
| `GET` | có | có | tra cứu hóa đơn, danh sách |
| `HEAD` | có | có | kiểm tra tồn tại (ít dùng) |
| `PUT` | không | **có** | thay toàn bộ tài nguyên — *không* dùng cho hóa đơn đã phát hành |
| `DELETE` | không | **có** | hủy bản nháp |
| `POST` | không | **không** | tạo hóa đơn, tạo bản điều chỉnh |
| `PATCH` | không | không (tùy định dạng) | sửa bản nháp |

Idempotent **không** có nghĩa là response giống nhau: `DELETE /drafts/42` lần đầu trả `204`, lần hai trả `404` — vẫn idempotent vì trạng thái server sau hai lần giống sau một lần.

<!-- placeholder-methods -->

<!-- fig:methods -->
<figure markdown="span">
  ![Tính chất của các method HTTP theo RFC 9110](assets/figures/02/methods.light.svg#only-light){ loading=lazy }
  ![Tính chất của các method HTTP theo RFC 9110](assets/figures/02/methods.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 2.1 — Tính chất của các method HTTP theo RFC 9110.</figcaption>
</figure>
<!-- /fig -->

### 1.3. Ví dụ số: vì sao `POST` tạo hóa đơn cần idempotency

Máy POS gửi `POST /v1/invoices`, server ghi hóa đơn thành công, nhưng response bị mất (Wi-Fi rớt, timeout ở load balancer). POS không biết hóa đơn đã được tạo chưa và **gửi lại**. Không có cơ chế chống trùng, khách hàng có hai hóa đơn.

Giả định: 60% của 1,8 triệu request là `POST` → $N = 1{,}08 \times 10^6$ lần tạo/ngày; tỷ lệ "server đã ghi nhưng client không nhận được response" $p = 0{,}1\%$ (Wi-Fi quán cà phê, 4G). Số hóa đơn trùng kỳ vọng mỗi ngày:

$$
\mathbb{E}[\text{trùng}] = N \cdot p = 1{,}08 \times 10^6 \times 10^{-3} \approx 1.080 \text{ hóa đơn/ngày}.
$$

Mỗi hóa đơn trùng phải xử lý bằng nghiệp vụ điều chỉnh/hủy theo quy định hóa đơn điện tử — tốn công kế toán của khách. Giải pháp chuẩn: client sinh một **khóa idempotency** (UUID) cho mỗi *ý định* tạo hóa đơn và gửi trong header `Idempotency-Key`; server lưu kết quả lần đầu theo khóa đó và trả lại đúng kết quả ấy cho mọi lần gửi lại. IETF đang chuẩn hóa header này (draft `httpapi-idempotency-key-header`); Stripe đã dùng mô hình này từ lâu. Thiết kế lưu trữ (bảng, khóa duy nhất, trạng thái "đang xử lý", thời hạn) ở Module 10.

<!-- placeholder-idempotency -->

<!-- fig:idempotency -->
<figure markdown="span">
  ![Trái: luồng gửi lại an toàn nhờ Idempotency-Key](assets/figures/02/idempotency.light.svg#only-light){ loading=lazy }
  ![Trái: luồng gửi lại an toàn nhờ Idempotency-Key](assets/figures/02/idempotency.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 2.2 — Trái: luồng gửi lại an toàn nhờ Idempotency-Key. Phải: số hóa đơn trùng kỳ vọng mỗi ngày nếu thiếu cơ chế này, theo tỷ lệ mất response p.</figcaption>
</figure>
<!-- /fig -->

### 1.4. Status code cho `invoice-api`

| Tình huống | Code | Ghi chú |
|---|---|---|
| Tạo hóa đơn thành công | `201 Created` + header `Location: /v1/invoices/{id}` | không phải `200` |
| Gửi lại với cùng `Idempotency-Key`, cùng nội dung | `201` (kết quả đã lưu) | client không cần phân biệt lần đầu hay lần sau |
| Cùng `Idempotency-Key`, **khác** nội dung | `422` hoặc `409` | client dùng lại khóa sai cách |
| JSON hỏng cú pháp | `400 Bad Request` | — |
| JSON đúng cú pháp, sai schema/quy tắc | `422 Unprocessable Content` | mặc định của FastAPI; RFC 9110 đổi tên từ "Unprocessable Entity" |
| Thiếu/sai token | `401 Unauthorized` + `WWW-Authenticate` | thực chất là "chưa xác thực" |
| Token hợp lệ, không có quyền | `403 Forbidden` | — |
| Hóa đơn của tenant khác | `404 Not Found` | **không** trả `403` — tránh tiết lộ sự tồn tại (Module 11) |
| Số hóa đơn đã tồn tại | `409 Conflict` | — |
| Body quá lớn | `413 Content Too Large` | chặn ở tầng 0 (Module 01) |
| Sai `Content-Type` | `415 Unsupported Media Type` | — |
| Vượt hạn mức | `429 Too Many Requests` + `Retry-After` | Module 11 |
| Quá tải, đang khởi động/tắt | `503 Service Unavailable` + `Retry-After` | readiness probe (Module 13) |

Lỗi trả về nên theo **Problem Details (RFC 9457, 2023)** — một object JSON có `type`, `title`, `status`, `detail`, `instance` và các trường mở rộng (ví dụ `errors` chứa danh sách lỗi validation có `loc`). Module 07 cài một exception handler biến `ValidationError` của Pydantic thành Problem Details.

### 1.5. Phiên bản HTTP và hệ quả cho server Python

- **HTTP/1.1**: một kết nối TCP xử lý tuần tự từng request; **keep-alive** cho phép dùng lại kết nối. Uvicorn mặc định đóng kết nối rảnh sau **5 giây** (`--timeout-keep-alive 5`).
- **HTTP/2**: nhiều stream song song trên một kết nối, nén header. Thường được **kết thúc ở load balancer/reverse proxy** (nginx, Envoy, ALB), proxy nói HTTP/1.1 với Uvicorn phía sau.
- **HTTP/3 (QUIC)**: chạy trên UDP, giảm head-of-line blocking ở tầng vận chuyển; cũng kết thúc ở biên.

Thực tế triển khai `invoice-api`: client ↔ (HTTP/2, TLS) ↔ load balancer ↔ (HTTP/1.1, mạng nội bộ) ↔ Uvicorn. Vì vậy hiệu năng của **bộ phân tích HTTP/1.1** trong Uvicorn (`h11` thuần Python hay `httptools` viết bằng C) có ý nghĩa thực tế — mục 6 và Module 09 đo khác biệt này.

---

## 2. REST: phong cách kiến trúc, không phải giao thức

### 2.1. Fielding 2000

Roy Fielding định nghĩa REST trong luận án tiến sĩ (UC Irvine, 2000) như một tập **ràng buộc kiến trúc** được rút ra từ thiết kế của Web:

1. **Client–server**: tách giao diện và lưu trữ.
2. **Stateless**: mỗi request mang đủ thông tin để hiểu; server không giữ trạng thái phiên giữa các request. → mở rộng ngang dễ dàng (request nào cũng đến được worker nào).
3. **Cache**: response tự đánh dấu có cache được hay không.
4. **Uniform interface**: định danh tài nguyên bằng URI; thao tác qua *biểu diễn* (representation); thông điệp tự mô tả; **hypermedia là động cơ của trạng thái ứng dụng** (HATEOAS).
5. **Layered system**: client không biết mình nói chuyện trực tiếp với server hay qua proxy.
6. **Code-on-demand** (tùy chọn).

Phần lớn API "REST" ngày nay thỏa 1, 2, 3, 5 và một phần của 4, nhưng bỏ HATEOAS. Đó không phải lỗi đạo đức; đó là lựa chọn kỹ thuật — client của `invoice-api` là phần mềm POS được lập trình sẵn, không phải trình duyệt khám phá liên kết. Gọi đúng tên ("HTTP API theo hướng tài nguyên") giúp tránh tranh cãi vô ích.

<!-- placeholder-rest -->

<!-- fig:rest -->
<figure markdown="span">
  ![Sáu ràng buộc REST và lựa chọn của invoice-api](assets/figures/02/rest.light.svg#only-light){ loading=lazy }
  ![Sáu ràng buộc REST và lựa chọn của invoice-api](assets/figures/02/rest.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 2.3 — Sáu ràng buộc REST và lựa chọn của invoice-api.</figcaption>
</figure>
<!-- /fig -->

### 2.2. Thiết kế tài nguyên cho `invoice-api`

```text
POST   /v1/invoices                      tạo hóa đơn (cần Idempotency-Key)
GET    /v1/invoices/{invoice_id}         lấy một hóa đơn
GET    /v1/invoices?issued_from=…&cursor=…   danh sách, phân trang theo cursor
POST   /v1/invoices/{invoice_id}/adjustments   lập hóa đơn điều chỉnh
POST   /v1/invoices/{invoice_id}/replacements  lập hóa đơn thay thế
POST   /v1/invoice-batches               gửi lô ≤ 500 hóa đơn → 202 Accepted + Location
GET    /v1/invoice-batches/{batch_id}    trạng thái lô
```

Ba quyết định đáng chú ý:

- **Không có `PUT`/`PATCH` trên hóa đơn đã phát hành.** Hóa đơn đã ký là bất biến về mặt pháp lý; mọi thay đổi là một tài nguyên mới (điều chỉnh/thay thế). API phản ánh đúng mô hình nghiệp vụ — một dạng "làm trạng thái phi pháp không biểu diễn được" (Module 01) ở tầng HTTP.
- **Batch là tài nguyên bất đồng bộ.** 500 hóa đơn × ~30 µs validation thì nhanh, nhưng ghi DB và gửi tổ chức truyền nhận thì không; trả `202 Accepted` và để client hỏi trạng thái thay vì giữ kết nối hàng chục giây.
- **Phiên bản trong path** (`/v1`) thay vì header: đơn giản cho client POS, dễ định tuyến ở load balancer. Chiến lược tiến hóa không phá vỡ client ở Module 12.

### 2.3. Phân trang: offset hay cursor?

Offset (`?page=200&size=50`) dịch thành `OFFSET 9950 LIMIT 50`: database vẫn phải duyệt và bỏ qua 9.950 dòng, chi phí $O(\text{offset} + \text{limit})$; thêm nữa, nếu có hóa đơn mới chèn vào giữa hai lần gọi, client thấy trùng hoặc sót.

Cursor (keyset) dùng giá trị khóa sắp xếp của phần tử cuối trang trước: `WHERE (issued_at, id) < (:last_issued_at, :last_id) ORDER BY issued_at DESC, id DESC LIMIT 50` — với index phù hợp, chi phí $O(\log n + \text{limit})$ bất kể trang thứ mấy, và ổn định khi có dữ liệu mới. Số đo thật (script `scripts/bench/bench_pagination.py`, SQLite, 1 triệu hóa đơn, có index): trang 1 cả hai mất ~0,03 ms; trang 1.000 offset mất ~1,8 ms; trang 19.000 offset mất **~42 ms** trong khi cursor vẫn **~0,07 ms**. `invoice-api` dùng cursor: một tenant lớn có hàng triệu hóa đơn.

<!-- placeholder-pagination -->

<!-- fig:pagination -->
<figure markdown="span">
  ![Số đo thật: thời gian lấy một trang 50 hóa đơn theo số thứ tự trang, phân trang offset so với cursor (keyset)](assets/figures/02/pagination.light.svg#only-light){ loading=lazy }
  ![Số đo thật: thời gian lấy một trang 50 hóa đơn theo số thứ tự trang, phân trang offset so với cursor (keyset)](assets/figures/02/pagination.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 2.4 — Số đo thật: thời gian lấy một trang 50 hóa đơn theo số thứ tự trang, phân trang offset so với cursor (keyset).</figcaption>
</figure>
<!-- /fig -->

---

## 3. Từ WSGI đến ASGI

### 3.1. WSGI (PEP 3333)

WSGI (2003, cập nhật PEP 3333 năm 2010) định nghĩa một ứng dụng web Python là một callable **đồng bộ**:

```python
def app(environ, start_response):
    start_response("200 OK", [("Content-Type", "text/plain")])
    return [b"xin chao"]
```

Mỗi request chiếm **một luồng (hoặc tiến trình) từ đầu đến cuối**. Mô hình này đơn giản, nhưng không biểu diễn được kết nối sống lâu (WebSocket, SSE) hay việc phục vụ hàng nghìn kết nối đang chờ I/O mà không cần hàng nghìn luồng.

### 3.2. ASGI

ASGI (Asynchronous Server Gateway Interface, đặc tả của dự án Django Channels, phiên bản 3.0) định nghĩa ứng dụng là một **coroutine** nhận ba tham số:

```python
async def app(scope, receive, send): ...
```

- **`scope`**: `dict` mô tả kết nối — `type` (`"http"`, `"websocket"`, `"lifespan"`), `method`, `path`, `headers`, `client`…
- **`receive`**: coroutine trả về sự kiện từ client, ví dụ `{"type": "http.request", "body": b"...", "more_body": False}`.
- **`send`**: coroutine gửi sự kiện tới client: `http.response.start` (status + headers), rồi một hoặc nhiều `http.response.body`.

Một ứng dụng ASGI hoàn chỉnh, không framework, chạy được với `uvicorn app:app`:

```python
# asgi_thuan.py — ứng dụng ASGI tối thiểu: echo độ dài body
import json

async def app(scope, receive, send):
    if scope["type"] == "lifespan":                 # khởi động / tắt
        while True:
            msg = await receive()
            if msg["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif msg["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    assert scope["type"] == "http"
    body = b""
    while True:                                      # body có thể đến thành nhiều mảnh
        msg = await receive()
        body += msg.get("body", b"")
        if not msg.get("more_body"):
            break
    payload = json.dumps({"path": scope["path"], "bytes": len(body)}).encode()
    await send({"type": "http.response.start", "status": 200,
                "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": payload})
```

```bash
uvicorn asgi_thuan:app --port 8000
curl -s -X POST localhost:8000/v1/invoices -d '{"total": 89100}'
# {"path": "/v1/invoices", "bytes": 16}
```

Mọi thứ FastAPI làm — routing, parse JSON, validate, DI, serialize — đều là code chạy bên trong một coroutine có chữ ký như trên. **Middleware** cũng chỉ là một ứng dụng ASGI bọc một ứng dụng ASGI khác:

```python
def timing_middleware(inner):
    async def app(scope, receive, send):
        import time
        t0 = time.perf_counter()
        async def send_wrapper(msg):
            if msg["type"] == "http.response.start":
                ms = (time.perf_counter() - t0) * 1000
                msg["headers"] = [*msg.get("headers", []), (b"server-timing", f"app;dur={ms:.1f}".encode())]
            await send(msg)
        await inner(scope, receive, send_wrapper)
    return app
```

<!-- placeholder-asgi -->

<!-- fig:asgi -->
<figure markdown="span">
  ![Server, middleware và ứng dụng đều nói chung một giao diện ASGI; request và response là các sự kiện qua receive/send](assets/figures/02/asgi.light.svg#only-light){ loading=lazy }
  ![Server, middleware và ứng dụng đều nói chung một giao diện ASGI; request và response là các sự kiện qua receive/send](assets/figures/02/asgi.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 2.5 — Server, middleware và ứng dụng đều nói chung một giao diện ASGI; request và response là các sự kiện qua receive/send.</figcaption>
</figure>
<!-- /fig -->

### 3.3. Lifespan

Sự kiện `lifespan.startup`/`lifespan.shutdown` cho phép mở tài nguyên dùng chung **một lần mỗi tiến trình** (pool kết nối DB, HTTP client, model ML) và đóng chúng khi tắt. FastAPI bọc cơ chế này trong tham số `lifespan=` dùng `asynccontextmanager` (Module 07, 13). Quy tắc: tài nguyên đắt khởi tạo trong lifespan; **không** khởi tạo trong mỗi request, **không** khởi tạo lúc import module (khó test, chạy cả khi chỉ import để sinh OpenAPI).

---

## 4. Event loop: một luồng, hàng nghìn kết nối

### 4.1. Vấn đề C10K

Năm 1999, Dan Kegel đặt câu hỏi "làm sao một server phục vụ 10.000 client đồng thời?" (*The C10K problem*). Mô hình một luồng/kết nối gặp giới hạn bộ nhớ (mỗi luồng có stack riêng) và chi phí chuyển ngữ cảnh. Lời giải là **I/O hướng sự kiện**: hệ điều hành cung cấp `select`/`poll`/`epoll` (Linux)/`kqueue` (BSD, macOS) để một luồng hỏi "trong hàng nghìn socket này, socket nào đã sẵn sàng đọc/ghi?" rồi chỉ xử lý những socket đó.

### 4.2. Tranh luận threads vs events

Hai bài viết kinh điển đứng ở hai phía:

- **Ousterhout (1996), *Why Threads Are A Bad Idea (for most purposes)***: luồng khó lập trình đúng (khóa, deadlock, khó debug); sự kiện đơn giản hơn cho hầu hết mục đích, luồng chỉ nên dùng khi cần song song CPU thật.
- **von Behren, Condit & Brewer (HotOS 2003), *Why Events Are A Bad Idea (for high-concurrency servers)***: lập trình hướng sự kiện làm vỡ luồng điều khiển thành các callback ("stack ripping"), khó đọc; các nhược điểm của luồng đến từ *cài đặt* chứ không phải từ *mô hình*, và luồng nhẹ có thể đạt hiệu năng tương đương.

`async`/`await` của Python (PEP 492, 2015) là một cách hòa giải: bên dưới là **sự kiện** (một event loop, I/O không chặn), bên trên là **cú pháp tuần tự** như luồng. Coroutine là một hàm có thể tạm dừng ở `await` và tiếp tục sau — trình biên dịch biến nó thành máy trạng thái, nên không có "stack ripping" trong code bạn viết. Cái giá: tính hợp tác (cooperative) — **mọi** chỗ chờ phải là `await`; một lời gọi chặn không có `await` đứng toàn bộ vòng lặp.

### 4.3. Bên trong vòng lặp asyncio

Một vòng lặp của asyncio (đơn giản hóa từ `BaseEventLoop._run_once`):

1. Tính thời gian chờ tối đa = thời điểm timer gần nhất − bây giờ (0 nếu hàng đợi ready không rỗng).
2. Gọi `selector.select(timeout)` — luồng **ngủ trong kernel** đến khi có socket sẵn sàng hoặc hết thời gian.
3. Với mỗi socket sẵn sàng, đưa callback tương ứng vào **hàng đợi ready**.
4. Chuyển các timer đã đến hạn (heap theo thời gian) vào hàng đợi ready.
5. Chạy **lần lượt** mọi callback trong hàng đợi ready. Mỗi callback thường là "tiếp tục coroutine X cho đến `await` kế tiếp".

<!-- placeholder-event-loop -->

<!-- fig:event-loop -->
<figure markdown="span">
  ![Một vòng của event loop asyncio và hệ quả của một lời gọi chặn](assets/figures/02/event-loop.light.svg#only-light){ loading=lazy }
  ![Một vòng của event loop asyncio và hệ quả của một lời gọi chặn](assets/figures/02/event-loop.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 2.6 — Một vòng của event loop asyncio và hệ quả của một lời gọi chặn.</figcaption>
</figure>
<!-- /fig -->

Bước 5 là chỗ mấu chốt: các callback chạy **tuần tự trên một luồng**. Nếu một coroutine chạy 50 ms CPU (hoặc gọi `time.sleep(0.05)`, `requests.get`, driver DB đồng bộ) trước `await` kế tiếp, **mọi** kết nối khác chờ 50 ms. Module 09 đo hiệu ứng này: một endpoint `async def` gọi `time.sleep(0.05)` giới hạn **cả tiến trình** ở ~20 request/giây, bất kể có bao nhiêu kết nối.

### 4.4. Ví dụ số: chi phí bộ nhớ của luồng và coroutine

<!-- placeholder-mem -->

<!-- fig:mem -->
<figure markdown="span">
  ![Số đo thật: RSS tăng thêm và thời gian tạo khi giữ n luồng hệ điều hành so với n task asyncio đang chờ](assets/figures/02/mem.light.svg#only-light){ loading=lazy }
  ![Số đo thật: RSS tăng thêm và thời gian tạo khi giữ n luồng hệ điều hành so với n task asyncio đang chờ](assets/figures/02/mem.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 2.7 — Số đo thật: RSS tăng thêm và thời gian tạo khi giữ n luồng hệ điều hành so với n task asyncio đang chờ.</figcaption>
</figure>
<!-- /fig -->

Mỗi luồng hệ điều hành có stack riêng (mặc định 8 MB *bộ nhớ ảo* trên Linux, chỉ phần đã chạm tới mới thành bộ nhớ thật) cùng cấu trúc kernel; mỗi coroutine asyncio chỉ là một object Python (frame + Task) cỡ vài KB. Hình trên là số đo thật trên máy của khóa (script `scripts/bench/bench_threads_coroutines.py`): RSS tăng thêm khi giữ $n$ luồng đang chờ so với $n$ task asyncio đang chờ. Kết quả: khoảng **16 KB mỗi luồng** (cộng ~0,16 ms để tạo) so với khoảng **0,9 KB mỗi task** (~4,5 µs để tạo) — chênh gần 18 lần về bộ nhớ; 100.000 task chiếm ~88 MB, trong khi 5.000 luồng đã chiếm ~79 MB. Với `ai-gateway`, 60 kết nối SSE mở hàng giờ cộng vài lượt LLM đang chờ — coroutine là lựa chọn tự nhiên.

---

## 5. GIL và free-threading

### 5.1. GIL là gì

CPython có **Global Interpreter Lock**: tại mỗi thời điểm chỉ một luồng thực thi bytecode Python. Luồng giữ GIL nhả nó khi chờ I/O (đọc socket, `time.sleep`) và định kỳ theo **switch interval** (mặc định 5 ms, `sys.getswitchinterval()`). Hệ quả:

- **I/O-bound đa luồng: tốt.** Khi luồng A chờ mạng, luồng B chạy. Đây là lý do FastAPI chạy endpoint `def` trong threadpool vẫn hiệu quả cho I/O.
- **CPU-bound đa luồng thuần Python: không nhanh hơn.** Bốn luồng tính toán chia nhau một GIL → tổng thời gian xấp xỉ một luồng, thậm chí chậm hơn vì tranh khóa.
- **Số đo thật** (script `bench_gil.py`, cùng tổng khối lượng tính toán thuần Python, 4 vCPU): 1/2/4 luồng mất 0,39/0,46/0,50 s — thêm luồng còn **chậm hơn**; 1/2/4 tiến trình mất 0,53/0,25/0,16 s — tăng tốc gần tuyến tính (tiến trình đơn chậm hơn luồng đơn vì chi phí khởi tạo và truyền dữ liệu giữa tiến trình).
- **Code native nhả GIL**: thư viện C/Rust có thể nhả GIL trong phần tính toán nặng (NumPy làm điều này với nhiều phép toán). pydantic-core chạy validation bằng Rust nhưng thao tác trên object Python, nên phần lớn thời gian vẫn giữ GIL.

<!-- placeholder-gil -->

<!-- fig:gil -->
<figure markdown="span">
  ![Số đo thật: chia cùng một khối lượng CPU thuần Python cho luồng (chung GIL) và tiến trình](assets/figures/02/gil.light.svg#only-light){ loading=lazy }
  ![Số đo thật: chia cùng một khối lượng CPU thuần Python cho luồng (chung GIL) và tiến trình](assets/figures/02/gil.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 2.8 — Số đo thật: chia cùng một khối lượng CPU thuần Python cho luồng (chung GIL) và tiến trình.</figcaption>
</figure>
<!-- /fig -->

### 5.2. Free-threading (PEP 703, PEP 779)

PEP 703 (2023) đề xuất bản build CPython **không có GIL**; Python 3.13 có bản build thử nghiệm (`python3.13t`), và **Python 3.14 nâng nó lên mức được hỗ trợ chính thức** theo các tiêu chí của PEP 779 (chấp nhận 06/2025): chậm hơn bản có GIL trên một luồng không quá ~15% (các bài phân tích báo cáo khoảng 5–10% ở 3.14), tốn thêm bộ nhớ có giới hạn. Đây vẫn là **bản build riêng**; bản mặc định vẫn có GIL.

Ý nghĩa với FastAPI, tính đến 10/2026:

- Endpoint `def` chạy trong threadpool **có thể** song song CPU thật trên bản free-threaded — validation nặng, serialize lớn, tính toán. Nhưng mọi extension (pydantic-core, driver DB, orjson…) phải có wheel cho bản free-threaded (hậu tố `t`, ví dụ `cp314t`) và phải an toàn luồng; hãy kiểm tra từng thư viện trước khi chuyển.
- Mô hình chuẩn hiện nay vẫn là **nhiều tiến trình** (Uvicorn `--workers`, hoặc nhiều pod) để dùng nhiều core cho việc nặng CPU, mỗi tiến trình một event loop. Module 09 đo throughput theo số worker.

---

## 6. Uvicorn: từ socket đến coroutine

### 6.1. Cấu trúc

Uvicorn gồm: (1) vòng lặp sự kiện (`asyncio` thuần, hoặc `uvloop` — viết bằng Cython trên libuv, nhanh hơn); (2) **protocol HTTP** — một `asyncio.Protocol` nhận byte từ socket và phân tích HTTP/1.1 bằng `h11` (thuần Python) hoặc `httptools` (binding của bộ phân tích C của Node.js); (3) cầu nối ASGI tạo `scope`, cài `receive`/`send` và chạy `app(scope, receive, send)` như một Task.

Chọn tự động: nếu cài `httptools`/`uvloop` (qua `pip install "uvicorn[standard]"`), chế độ `auto` dùng chúng; nếu chỉ `pip install uvicorn`, bạn chạy `h11` + asyncio thuần. Đây là một khác biệt hiệu năng **âm thầm**: cùng code, cùng lệnh chạy, khác gói cài đặt. Đo trên máy của khóa (1 worker, 32 kết nối): `GET /health` tăng từ ~4.250 lên ~8.200 req/s, `POST /invoices` (hóa đơn 12 dòng) từ ~2.370 lên ~4.040 req/s khi chuyển từ h11 + asyncio sang httptools + uvloop. Phần lớn lợi ích đến từ bộ phân tích HTTP; uvloop góp thêm khoảng 10–15%.

<!-- placeholder-uvicorn-variants -->

<!-- fig:uvicorn-variants -->
<figure markdown="span">
  ![Số đo thật: throughput của cùng ứng dụng với bốn tổ hợp bộ phân tích HTTP và event loop của Uvicorn](assets/figures/02/uvicorn-variants.light.svg#only-light){ loading=lazy }
  ![Số đo thật: throughput của cùng ứng dụng với bốn tổ hợp bộ phân tích HTTP và event loop của Uvicorn](assets/figures/02/uvicorn-variants.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 2.9 — Số đo thật: throughput của cùng ứng dụng với bốn tổ hợp bộ phân tích HTTP và event loop của Uvicorn.</figcaption>
</figure>
<!-- /fig -->

### 6.2. Các tham số vận hành quan trọng (Uvicorn 0.54)

| Tham số | Mặc định | Ý nghĩa |
|---|---|---|
| `--workers` | 1 | số tiến trình (mỗi tiến trình một event loop) |
| `--backlog` | 2048 | hàng đợi kết nối chờ `accept` trong kernel |
| `--limit-concurrency` | không giới hạn | vượt ngưỡng → trả `503` thay vì nhận thêm (load shedding thô) |
| `--timeout-keep-alive` | 5 s | đóng kết nối rảnh |
| `--timeout-graceful-shutdown` | không giới hạn | thời gian chờ request đang chạy khi tắt |
| `--http`, `--loop` | `auto` | chọn bộ phân tích HTTP và vòng lặp |
| `--proxy-headers`, `--forwarded-allow-ips` | — | tin `X-Forwarded-*` từ load balancer (Module 13) |

### 6.3. Hành trình của `POST /v1/invoices`

<!-- placeholder-journey -->

<!-- fig:journey -->
<figure markdown="span">
  ![Chín bước của một request POST /v1/invoices, tô màu theo thành phần chịu trách nhiệm](assets/figures/02/journey.light.svg#only-light){ loading=lazy }
  ![Chín bước của một request POST /v1/invoices, tô màu theo thành phần chịu trách nhiệm](assets/figures/02/journey.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 2.10 — Chín bước của một request POST /v1/invoices, tô màu theo thành phần chịu trách nhiệm.</figcaption>
</figure>
<!-- /fig -->

1. **Kernel** nhận gói TCP, đưa byte vào bộ đệm socket; `epoll` báo socket sẵn sàng đọc.
2. **Event loop** gọi `data_received` của protocol HTTP; bộ phân tích (h11/httptools) dựng request line + header.
3. Uvicorn tạo `scope` và chạy `app(scope, receive, send)` như một Task mới.
4. **Middleware** (CORS, nén, đo thời gian, telemetry…) lần lượt bọc lời gọi.
5. **Starlette Router** khớp path + method với route.
6. **FastAPI** đọc body (qua `receive`), giải đồ thị dependency (xác thực tenant, session DB), gọi Pydantic **parse + validate** body thành `Invoice` — lỗi thì trả `422` ngay.
7. **Handler** của bạn chạy (trên event loop nếu `async def`, trong threadpool nếu `def`).
8. Kết quả đi qua **response model** (lọc trường, serialize bằng Pydantic) → `send(http.response.start)` + `send(http.response.body)`.
9. Dependency có `yield` dọn dẹp (commit/rollback, trả kết nối về pool); protocol ghi byte ra socket; kết nối giữ lại cho request kế tiếp (keep-alive).

Module 07 phóng to bước 4–8; Module 08 phóng to bước 6 (dependency); Module 09 phóng to bước 7.

---

## Lỗi thường gặp & cách xử lý

| Triệu chứng | Nguyên nhân gốc | Cách xử lý |
|---|---|---|
| Khách có hóa đơn trùng sau sự cố mạng | `POST` không idempotent, client gửi lại | `Idempotency-Key` + lưu kết quả theo khóa (Module 10) |
| Trả `200` cho mọi thứ, lỗi nằm trong body | Không dùng ngữ nghĩa status code | `201`/`4xx`/`5xx` đúng nghĩa + Problem Details (RFC 9457) |
| Lộ sự tồn tại hóa đơn của tenant khác | Trả `403` cho tài nguyên không thuộc quyền | Trả `404` như thể không tồn tại |
| Trang danh sách sâu chậm dần, trùng/sót bản ghi | Phân trang offset | Cursor/keyset + index phù hợp |
| Một endpoint chậm làm cả service chậm | Lời gọi chặn trong `async def` chặn event loop | Dùng thư viện async, hoặc khai báo `def`, hoặc `run_in_threadpool` (Module 09) |
| Throughput thấp bất thường dù code giống hệt môi trường khác | Cài `uvicorn` không có `[standard]` → h11 + asyncio thuần | Cài `uvicorn[standard]`, kiểm tra log khởi động/`--http httptools` |
| Thêm luồng không làm code CPU-bound nhanh hơn | GIL | Nhiều tiến trình; hoặc thư viện native nhả GIL; cân nhắc free-threaded khi thư viện hỗ trợ |
| Mở pool DB trong mỗi request | Không dùng lifespan | Khởi tạo tài nguyên đắt trong lifespan, chia sẻ qua dependency |

## Tóm tắt (cheat-sheet)

- **Safe** ⊂ **idempotent**: `GET/HEAD` safe; `PUT/DELETE` idempotent; `POST` không → cần `Idempotency-Key`. Thiếu nó: ~$N \cdot p$ bản trùng/ngày (≈1.080 với giả định của case).
- Status: `201`+`Location`, `400` cú pháp, `422` schema, `401` chưa xác thực, `403` không quyền, `404` cho tài nguyên tenant khác, `409`, `413`, `415`, `429`+`Retry-After`, `503`. Lỗi theo RFC 9457.
- REST = ràng buộc kiến trúc (Fielding 2000): stateless, cache, uniform interface, layered. Hầu hết API là "HTTP API hướng tài nguyên" — chấp nhận được.
- Hóa đơn đã phát hành bất biến → điều chỉnh/thay thế là tài nguyên mới; batch → `202` + tài nguyên trạng thái; phân trang cursor $O(\log n + k)$.
- ASGI: `async def app(scope, receive, send)`; middleware là app bọc app; lifespan mở/đóng tài nguyên mỗi tiến trình.
- Event loop: `select` → hàng đợi ready → chạy tuần tự callback. Một lời gọi chặn đứng **mọi** kết nối của tiến trình.
- GIL: tốt cho I/O đa luồng, vô ích cho CPU thuần Python đa luồng → nhiều tiến trình. Free-threaded được hỗ trợ chính thức từ 3.14 (bản build riêng).
- `uvicorn[standard]` (httptools + uvloop) vs `uvicorn` (h11 + asyncio): cùng code, khác throughput.

## Câu hỏi tự kiểm tra / phỏng vấn

1. `DELETE /v1/drafts/42` lần đầu trả `204`, lần hai trả `404`. Nó có idempotent không? Vì sao?

    <details markdown="1"><summary>Gợi ý</summary>
    Có. Idempotency xét trạng thái server sau các lần gọi (bản nháp không còn tồn tại), không xét response giống nhau.
    </details>

2. Thiết kế cơ chế để POS gửi lại `POST /v1/invoices` an toàn. Server cần lưu gì, trong bao lâu?

    <details markdown="1"><summary>Gợi ý</summary>
    Client sinh `Idempotency-Key` (UUID) cho mỗi ý định tạo. Server lưu (tenant, key) → trạng thái (đang xử lý/xong), hash của request body, response (status + body). Lần gửi lại cùng key + cùng hash → trả response đã lưu; khác hash → 422/409; đang xử lý → 409 hoặc chờ. Giữ ít nhất lâu hơn cửa sổ retry của client (ví dụ 24–72 giờ). Chi tiết Module 10.
    </details>

3. Vì sao trả `404` thay vì `403` khi tenant A truy cập hóa đơn của tenant B?

    <details markdown="1"><summary>Gợi ý</summary>
    `403` xác nhận tài nguyên tồn tại, cho phép kẻ tấn công dò ID hợp lệ (enumeration). `404` không tiết lộ gì. Đây là phòng thủ cho BOLA (OWASP API1, Module 11).
    </details>

4. Ràng buộc "stateless" của REST giúp gì cho việc mở rộng `invoice-api` lên nhiều worker/pod?

    <details markdown="1"><summary>Gợi ý</summary>
    Request nào cũng đến được worker nào (load balancer không cần sticky session), worker có thể thêm/bớt/khởi động lại tự do; trạng thái nằm ở DB/Redis, không ở bộ nhớ tiến trình.
    </details>

5. So sánh độ phức tạp của phân trang offset và cursor khi client đọc trang thứ 10.000.

    <details markdown="1"><summary>Gợi ý</summary>
    Offset: DB duyệt và bỏ qua offset dòng, $O(\text{offset} + k)$. Cursor với index (issued_at, id): tìm vị trí bằng B-tree $O(\log n)$ rồi đọc $k$ dòng, không phụ thuộc trang thứ mấy.
    </details>

6. Viết chữ ký một ứng dụng ASGI và giải thích ba tham số.

    <details markdown="1"><summary>Gợi ý</summary>
    `async def app(scope, receive, send)`. `scope`: dict mô tả kết nối (type, method, path, headers…). `receive`: await để lấy sự kiện từ client (body từng mảnh, disconnect). `send`: await để gửi sự kiện tới client (response.start, response.body).
    </details>

7. Một coroutine gọi `requests.get(url)` (thư viện đồng bộ) mất 300 ms. Điều gì xảy ra với 100 request khác đang được xử lý trên cùng tiến trình?

    <details markdown="1"><summary>Gợi ý</summary>
    Chúng đứng chờ 300 ms vì event loop bị chặn — không callback nào khác chạy được. Sửa: dùng `httpx.AsyncClient` + `await`, hoặc chạy trong threadpool, hoặc khai báo endpoint là `def`.
    </details>

8. Vì sao bốn luồng Python tính toán thuần không nhanh hơn một luồng trên bản CPython mặc định? Python 3.14 thay đổi điều gì?

    <details markdown="1"><summary>Gợi ý</summary>
    GIL cho phép một luồng chạy bytecode tại một thời điểm. 3.14 hỗ trợ chính thức bản build free-threaded (không GIL) như một bản build riêng; luồng có thể song song thật nếu mọi extension hỗ trợ, đổi lại chậm hơn một ít trên một luồng.
    </details>

9. Kể các bước từ lúc byte đến socket cho tới khi handler `create_invoice` được gọi.

    <details markdown="1"><summary>Gợi ý</summary>
    Kernel → epoll báo sẵn sàng → event loop gọi protocol → phân tích HTTP → tạo scope, chạy app Task → middleware → router khớp route → FastAPI đọc body, giải dependency, Pydantic validate → gọi handler.
    </details>

## Bài tập thực hành

1. **ASGI không framework (CPU, 15 phút).** Chạy `asgi_thuan.py` ở mục 3.2 bằng `uvicorn`. Thêm: trả `413` nếu body > 2 MB (đếm dần theo từng mảnh, dừng đọc ngay khi vượt), và `415` nếu `content-type` không phải `application/json`.
2. **Middleware đo thời gian (CPU, 10 phút).** Gắn `timing_middleware` vào app ở bài 1, kiểm tra header `server-timing` bằng `curl -i`. Giải thích vì sao phải bọc `send` chứ không đo sau `await inner(...)`.
3. **Chặn event loop (CPU, 15 phút).** Viết một app ASGI có hai path: `/fast` trả ngay, `/slow` gọi `time.sleep(1)`. Gửi đồng thời 1 request `/slow` và 10 request `/fast` (dùng `httpx.AsyncClient` hoặc `curl` song song); đo latency của `/fast`. Đổi `time.sleep` thành `await asyncio.sleep` và đo lại.
4. **Thiết kế tài nguyên (giấy, 20 phút).** Thiết kế API cho tính năng "khách hàng (người mua) tra cứu hóa đơn bằng mã tra cứu in trên hóa đơn giấy": URI, method, status code, cơ chế chống dò mã (rate limit, độ dài mã), phân trang nếu cần.

## Tài liệu tham khảo

Tiêu chuẩn và đặc tả:

- Fielding, R., Nottingham, M., Reschke, J. (2022). *RFC 9110: HTTP Semantics*. https://www.rfc-editor.org/rfc/rfc9110
- Nottingham, M., Wilde, E., Dalal, S. (2023). *RFC 9457: Problem Details for HTTP APIs*. https://www.rfc-editor.org/rfc/rfc9457
- IETF HTTPAPI WG. *The Idempotency-Key HTTP Header Field* (Internet-Draft). https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/
- PEP 3333 — *Python Web Server Gateway Interface v1.0.1*. https://peps.python.org/pep-3333/
- ASGI Specification. https://asgi.readthedocs.io/en/latest/specs/main.html
- PEP 492 — *Coroutines with async and await syntax*. https://peps.python.org/pep-0492/
- PEP 703 — *Making the Global Interpreter Lock Optional in CPython*; PEP 779 — *Criteria for supported status for free-threaded Python*. https://peps.python.org/pep-0703/ , https://peps.python.org/pep-0779/

Paper và bài viết kinh điển:

- Fielding, R. T. (2000). *Architectural Styles and the Design of Network-based Software Architectures*. Luận án tiến sĩ, UC Irvine. https://ics.uci.edu/~fielding/pubs/dissertation/top.htm
- Kegel, D. (1999, cập nhật sau). *The C10K problem*. http://www.kegel.com/c10k.html
- Ousterhout, J. (1996). *Why Threads Are A Bad Idea (for most purposes)*. USENIX Technical Conference (bài nói). https://users.cs.utah.edu/~regehr/research/ouster.pdf
- von Behren, R., Condit, J., Brewer, E. (2003). *Why Events Are A Bad Idea (for high-concurrency servers)*. HotOS IX, pp. 19–24. https://cs.uwaterloo.ca/~brecht/servers/readings-new/vonbehren-events-bad-2003.pdf
- Fowler, M. (2010). *Richardson Maturity Model*. https://martinfowler.com/articles/richardsonMaturityModel.html

Tài liệu chính thức (tra cứu 10/2026):

- Uvicorn — Settings. https://www.uvicorn.org/settings/
- Python docs — `asyncio` Event Loop; `sys.getswitchinterval`. https://docs.python.org/3/library/asyncio-eventloop.html
- Python docs — *Python support for free threading*. https://docs.python.org/3/howto/free-threading-python.html
