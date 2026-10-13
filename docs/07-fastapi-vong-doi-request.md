# Module 07 — FastAPI: vòng đời một request

> Thời lượng: ~50 phút · Mức độ: Trung bình · Tiên quyết: Module 02, Module 03

Module 02 đã dựng hành trình 9 bước của `POST /v1/invoices` từ socket đến handler. Module này phóng to các bước 4–8 — phần thuộc về Starlette và FastAPI — và trả lời những câu hỏi mà mọi người dùng FastAPI sớm muộn sẽ gặp: *FastAPI biết lấy tham số ở đâu bằng cách nào? Vì sao một trường thừa trong dict trả về không lộ ra response? Middleware chạy theo thứ tự nào, và vì sao một dòng `@app.middleware("http")` có thể làm API chậm đi một nửa? Một request tốn bao nhiêu micro-giây cho khung sườn, bao nhiêu cho code của mình?* Mọi câu trả lời đều được kiểm chứng bằng cách đọc mã nguồn FastAPI 0.143 / Starlette 1.8 và đo.

## Mục tiêu học tập

Sau module này, bạn có thể:

1. Giải thích FastAPI biến **chữ ký hàm** thành cây `Dependant` lúc khởi động, và dự đoán **nguồn** (path, query, header, cookie, body) của mỗi tham số.
2. Mô tả đường đi của một request qua chồng middleware, router, đọc body, giải dependency, gọi handler, và serialize response — kể cả việc FastAPI parse body bằng `json.loads` rồi mới validate.
3. Dùng `response_model` / kiểu trả về để **lọc dữ liệu đi ra**, và giải thích khi nào response bị lỗi 500.
4. Thay định dạng lỗi 422 mặc định bằng **Problem Details (RFC 9457)**, không lộ `input` của client.
5. Sắp thứ tự middleware đúng, và chọn **ASGI middleware thuần** thay vì `BaseHTTPMiddleware` dựa trên số đo.
6. Dùng streaming **JSONL** và **SSE** tích hợp sẵn của FastAPI 0.143 cho `ai-gateway`.
7. Đọc phân rã thời gian của một request theo thư viện và biết phần nào thuộc về mình.

---

## 1. FastAPI dựng gì lúc khởi động

### 1.1. Từ chữ ký hàm đến `Dependant`

Khi bạn viết

```python
@app.post("/t/{tenant_id}/items")
def create(tenant_id: int, item: Item, x_request_id: Annotated[str | None, Header()] = None,
           dry_run: bool = False): ...
```

decorator **không** chạy gì liên quan đến request. Nó gọi `get_dependant(path, call)`: đọc chữ ký bằng `inspect`, đọc type hint (gồm metadata `Annotated`), và phân loại từng tham số vào một trong các danh sách `path_params`, `query_params`, `header_params`, `cookie_params`, `body_params`, `dependencies` (Module 08). Kết quả là một cây `Dependant` được lưu trên route. Đồng thời FastAPI dựng:

- **body field**: một trường Pydantic cho body. Nếu chỉ có một tham số body là model (`item: Item`), body chính là model đó. Nếu có **nhiều** tham số body, FastAPI **sinh ra một model mới** bọc chúng (kiểm chứng: schema tên `Body_two_two_post` trong OpenAPI) và client phải gửi `{"item": {...}, "note": "..."}`.
- **response field**: từ `response_model=` hoặc kiểu trả về (`-> InvoiceOut`).
- **schema OpenAPI** cho route.

<!-- placeholder-dependant -->

<!-- fig:dependant -->
<figure markdown="span">
  ![Lúc khai báo route, FastAPI phân tích chữ ký hàm thành cây Dependant và dựng sẵn body field, response field, schema OpenAPI](assets/figures/07/dependant.light.svg#only-light){ loading=lazy }
  ![Lúc khai báo route, FastAPI phân tích chữ ký hàm thành cây Dependant và dựng sẵn body field, response field, schema OpenAPI](assets/figures/07/dependant.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 7.1 — Lúc khai báo route, FastAPI phân tích chữ ký hàm thành cây Dependant và dựng sẵn body field, response field, schema OpenAPI.</figcaption>
</figure>
<!-- /fig -->

Mọi suy luận tốn kém (đọc chữ ký, dựng validator Pydantic) xảy ra **một lần lúc import**. Mỗi request chỉ đi theo cây đã dựng — cùng triết lý với core schema của Pydantic (Module 03).

### 1.2. Quy tắc chọn nguồn tham số

Kiểm chứng trên FastAPI 0.143:

| Khai báo | Nguồn | Ghi chú |
|---|---|---|
| tên khớp `{...}` trong path | path | `tenant_id: int` với path `/t/{tenant_id}/…` |
| kiểu đơn (`int`, `str`, `bool`, `Enum`, `list[int]`…), không khớp path | **query** | `dry_run: bool = False` → `?dry_run=yes` (lax: `"yes"` → `True`) |
| model Pydantic, không có marker | **body** (JSON) | `item: Item` |
| `Annotated[T, Header()]` | header | tên `x_request_id` → header `x-request-id` (gạch dưới thành gạch ngang) |
| `Annotated[T, Cookie()]` | cookie | |
| `Annotated[Model, Query()]` | **query, gom vào model** | model `Filters` có `extra="forbid"` → `?foo=1` bị 422 |
| `Annotated[T, Body()]`, `Body(embed=True)` | body | nhiều tham số body → body được bọc theo tên |
| `Annotated[T, Form()]`, `UploadFile` | form/multipart | cần gói `python-multipart` |
| `Request`, `Response`, `BackgroundTasks` | đối tượng đặc biệt | FastAPI tiêm vào, không validate |

Khi request sai ở nhiều nguồn cùng lúc, lỗi được **gom chung**: gửi `/t/abc/items` với `qty: 0` trả về một response 422 có hai lỗi, `loc` lần lượt là `["path", "tenant_id"]` và `["body", "qty"]` — phần tử đầu của `loc` cho biết nguồn.

---

## 2. Đường đi của một request

### 2.1. Chồng ứng dụng ASGI

`app.build_middleware_stack()` của Starlette bọc router theo thứ tự (đọc từ mã nguồn Starlette 1.8, ngoài vào trong):

1. `ServerErrorMiddleware` — bắt mọi ngoại lệ chưa xử lý, trả 500 (và gọi handler cho `Exception`/500 nếu có).
2. *(tùy chọn)* `RequestBodyLimitMiddleware` — giới hạn kích thước body (mới trong Starlette 1.x).
3. **Middleware của bạn**, theo thứ tự ngược với thứ tự `add_middleware` (mục 5).
4. `ExceptionMiddleware` — chuyển `HTTPException` và các ngoại lệ có handler thành response.
5. **Router** — khớp path + method, gọi route.

### 2.2. Bên trong route: `get_request_handler`

Đọc mã nguồn `fastapi/routing.py` (0.143), mỗi request vào route đi qua:

1. **Đọc body**: `await request.body()`; nếu `Content-Type` là `application/json` (hoặc `+json`), gọi `await request.json()` — tức **`json.loads` của thư viện chuẩn**. Body thiếu `Content-Type` **không** được parse thành JSON khi `strict_content_type=True` (mặc định, để chống CSRF qua request không cần preflight) → kiểm chứng: 422.
2. **Giải dependency** (`solve_dependencies`): lấy và validate tham số path/query/header/cookie, validate body (dict từ bước 1) bằng Pydantic, chạy các dependency con (Module 08). Mọi lỗi được gom lại → `RequestValidationError` → 422.
3. **Gọi handler**: `async def` chạy thẳng trên event loop; `def` chạy qua `run_in_threadpool` (Module 09).
4. **Serialize response** (`serialize_response`): nếu có response field, validate + lọc giá trị trả về rồi dump thành JSON; nếu không, chạy `jsonable_encoder`.
5. **Dọn dẹp**: dependency có `yield` chạy phần sau `yield` (Module 08).

<!-- placeholder-pipeline -->

<!-- fig:pipeline -->
<figure markdown="span">
  ![Chồng ứng dụng ASGI của Starlette (ngoài vào trong) và năm bước bên trong một route FastAPI, đọc từ mã nguồn 0](assets/figures/07/pipeline.light.svg#only-light){ loading=lazy }
  ![Chồng ứng dụng ASGI của Starlette (ngoài vào trong) và năm bước bên trong một route FastAPI, đọc từ mã nguồn 0](assets/figures/07/pipeline.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 7.2 — Chồng ứng dụng ASGI của Starlette (ngoài vào trong) và năm bước bên trong một route FastAPI, đọc từ mã nguồn 0.143 / Starlette 1.8.</figcaption>
</figure>
<!-- /fig -->

Chi tiết ở bước 1 có hệ quả hiệu năng đo được (Module 06, mục 4.2): đường mặc định là `json.loads` → dict → validate, chậm gấp đôi `model_validate_json`. Khi cần, có thể tự nhận byte:

```python
@app.post("/v1/invoices", status_code=201,
          openapi_extra={"requestBody": {"content": {"application/json": {
              "schema": InvoiceIn.model_json_schema(ref_template="#/components/schemas/{model}")}},
              "required": True}})
async def create_invoice(request: Request) -> InvoiceOut:
    try:
        inv = InvoiceIn.model_validate_json(await request.body())
    except ValidationError as e:
        # thêm "body" vào đầu loc để lỗi có cùng dạng với đường mặc định
        raise RequestValidationError([{**err, "loc": ("body", *err["loc"])}
                                      for err in e.errors(include_url=False)], body=None)
    ...
```

Đo trong tiến trình (mục 7): cùng model hóa đơn 12 dòng, endpoint khai báo `inv: Invoice` tốn ~135 µs/request, endpoint tự gọi `model_validate_json` ~86 µs. Cái giá: mất tài liệu OpenAPI tự động (phải khai báo tay qua `openapi_extra`) và mất các tham số body khác. Mình khuyên dùng đường mặc định cho mọi endpoint, chỉ chuyển sang đường thủ công cho **một vài endpoint nóng nhất** khi phân rã chi phí cho thấy đáng làm.

---

## 3. Response: lọc, kiểm tra, serialize

### 3.1. `response_model` là bộ lọc an ninh

```python
class Out(BaseModel):
    sku: str

@app.get("/leak", response_model=Out)
def leak():
    return {"sku": "A", "cost_price": 1000, "tenant_id": 9}    # dict có trường nội bộ

# GET /leak → {"sku": "A"}       — cost_price và tenant_id bị lọc
```

Kiểu trả về (`def leak2() -> Out`) có tác dụng tương tự. Đây là tuyến phòng thủ chính chống **lộ dữ liệu quá mức** (BOPLA — OWASP API3:2023, Module 11): handler có thể trả ORM row đầy đủ, response chỉ chứa những gì `InvoiceOut` khai báo (Module 05, mục 6).

### 3.2. Response sai → 500, không phải 422

```python
@app.get("/bad")
def bad() -> Out:
    return {"nope": 1}          # thiếu trường sku

# GET /bad → 500 Internal Server Error (ResponseValidationError)
```

422 nghĩa là *client* gửi sai; dữ liệu *server* tạo ra không khớp hợp đồng là lỗi của server. Đừng tắt kiểm tra này — nó bắt được bug thật (ví dụ ORM trả `None` cho trường bắt buộc). Trong test, lỗi này hiện rõ (Module 12).

### 3.3. Chi phí

Đo trong tiến trình (mục 7): trả `dict` không có response model (~153 µs) **chậm hơn** trả một `Created` model nhỏ (~135 µs), vì nhánh không có response model phải chạy `jsonable_encoder` duyệt dict bằng Python; trả lại **cả** hóa đơn 12 dòng qua `-> Invoice` (~149 µs). Kết luận thực dụng: luôn khai báo kiểu trả về — vừa an toàn, vừa không chậm hơn.

<!-- placeholder-response -->

<!-- fig:response -->
<figure markdown="span">
  ![Số đo thật trong tiến trình: chi phí một request theo cách khai báo body và response](assets/figures/07/response.light.svg#only-light){ loading=lazy }
  ![Số đo thật trong tiến trình: chi phí một request theo cách khai báo body và response](assets/figures/07/response.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 7.3 — Số đo thật trong tiến trình: chi phí một request theo cách khai báo body và response.</figcaption>
</figure>
<!-- /fig -->

---

## 4. Lỗi: từ 422 mặc định đến Problem Details

### 4.1. Định dạng mặc định

```json
{"detail": [
  {"type": "int_parsing", "loc": ["path", "tenant_id"],
   "msg": "Input should be a valid integer, unable to parse string as an integer", "input": "abc"},
  {"type": "greater_than", "loc": ["body", "qty"], "msg": "Input should be greater than 0",
   "input": 0, "ctx": {"gt": 0}}]}
```

Hai vấn đề với `invoice-api`: (1) không theo chuẩn — client phải viết code riêng cho từng API; (2) trường **`input` phản chiếu lại dữ liệu client gửi**, gồm cả mật khẩu, token, số thẻ nếu chúng nằm trong trường sai — và các response lỗi hay bị log ở proxy, APM, trình duyệt.

### 4.2. Problem Details (RFC 9457)

```python
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def problem_422(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, media_type="application/problem+json", content={
        "type": "https://api.mekong.example/problems/validation",
        "title": "Dữ liệu không hợp lệ",
        "status": 422,
        "instance": str(request.url.path),
        "errors": [{"field": ".".join(map(str, e["loc"][1:])), "source": e["loc"][0], "code": e["type"],
                    "message": VI.get(e["type"], e["msg"]).format(**(e.get("ctx") or {}))}   # VI: Module 03
                   for e in exc.errors()],
    })
```

Kiểm chứng: gửi `{"seq": "x"}` → `422`, `content-type: application/problem+json`, `errors = [{"field": "seq", "code": "int_parsing"}, {"field": "text", "code": "missing"}]` — không còn `input`.

Lỗi nghiệp vụ dùng cùng định dạng: định nghĩa ngoại lệ miền (`InvoiceNumberTaken`, `TaxCodeNotOwned`…) và một handler cho mỗi loại → `409`, `404`. Handler cho `Exception` chung trả 500 **không kèm chi tiết** (chi tiết vào log có trace id, Module 13).

<!-- placeholder-errors -->

<!-- fig:errors -->
<figure markdown="span">
  ![Định dạng 422 mặc định (có trường input phản chiếu dữ liệu) so với Problem Details theo RFC 9457](assets/figures/07/errors.light.svg#only-light){ loading=lazy }
  ![Định dạng 422 mặc định (có trường input phản chiếu dữ liệu) so với Problem Details theo RFC 9457](assets/figures/07/errors.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 7.4 — Định dạng 422 mặc định (có trường input phản chiếu dữ liệu) so với Problem Details theo RFC 9457.</figcaption>
</figure>
<!-- /fig -->

---

## 5. Middleware: thứ tự và cái giá

### 5.1. Thứ tự

Thí nghiệm với hai middleware `m1` (khai báo trước) và `m2` (khai báo sau):

```text
m2 vào → m1 vào → [handler] → m1 ra → m2 ra
```

**Middleware thêm sau nằm ngoài cùng.** Hệ quả: middleware đo thời gian/telemetry nên thêm **sau cùng** (ngoài cùng, đo được cả các middleware khác); CORS nên ở ngoài để xử lý preflight `OPTIONS` trước khi chạm tới xác thực.

### 5.2. `BaseHTTPMiddleware` so với ASGI thuần

`@app.middleware("http")` là cú pháp tiện cho `BaseHTTPMiddleware`: bạn viết `async def mw(request, call_next)` thay vì làm việc với `scope/receive/send`. Để có API tiện đó, Starlette phải chạy ứng dụng bên trong trong một task riêng và nối response qua một stream nội bộ. Số đo:

| Cấu hình (`GET /health`, 1 worker, httptools + uvloop, 32 kết nối) | request/giây | so với không có |
|---|---|---|
| không middleware | ~7.570 | — |
| 1 × `BaseHTTPMiddleware` | ~3.380 | **−55%** |
| 2 × `BaseHTTPMiddleware` | ~1.980 | −74% |
| 5 × `BaseHTTPMiddleware` | ~950 | **−87%** |
| 1 × ASGI thuần | ~8.870 | (trong nhiễu) |
| 5 × ASGI thuần | ~7.020 | (trong nhiễu) |

Đo trong tiến trình cho cùng kết luận: mỗi lớp `BaseHTTPMiddleware` cộng ~120 µs mỗi request, mỗi lớp ASGI thuần cộng gần 0. Với endpoint thật (validation, DB), tỷ lệ phần trăm nhỏ hơn vì phần việc khác lớn hơn, nhưng **~100–130 µs mỗi lớp** vẫn là chi phí tuyệt đối — ngang cả phần parse + validate hóa đơn.

<!-- placeholder-middleware -->

<!-- fig:middleware -->
<figure markdown="span">
  ![Số đo thật: throughput theo số lớp middleware trên server (trái) và chi phí mỗi lớp đo trong tiến trình (phải)](assets/figures/07/middleware.light.svg#only-light){ loading=lazy }
  ![Số đo thật: throughput theo số lớp middleware trên server (trái) và chi phí mỗi lớp đo trong tiến trình (phải)](assets/figures/07/middleware.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 7.5 — Số đo thật: throughput theo số lớp middleware trên server (trái) và chi phí mỗi lớp đo trong tiến trình (phải).</figcaption>
</figure>
<!-- /fig -->

Middleware gắn request id, viết bằng ASGI thuần:

```python
import uuid

class RequestIdMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        rid = headers.get(b"x-request-id", b"").decode()[:64] or uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = rid          # handler đọc qua request.state

        async def send_with_id(msg):
            if msg["type"] == "http.response.start":
                msg["headers"] = [*msg.get("headers", []), (b"x-request-id", rid.encode())]
            await send(msg)

        await self.app(scope, receive, send_with_id)

app.add_middleware(RequestIdMiddleware)
```

### 5.3. Middleware nên và không nên làm gì

| Nên | Không nên |
|---|---|
| CORS, nén (`GZipMiddleware`), `TrustedHostMiddleware` | Parse body để quyết định gì đó (parser differential, Module 01; đọc body hai lần) |
| request id, đo thời gian, telemetry | Xác thực/phân quyền theo từng endpoint — dùng dependency (Module 08, 11): có trong OpenAPI, test được, override được |
| giới hạn kích thước body (`RequestBodyLimitMiddleware`) | Truy vấn DB cho mọi request kể cả `/health` |

Giới hạn body đã có sẵn trong Starlette 1.x; với FastAPI, thêm như một middleware (kiểm chứng: body 2 KB vượt ngưỡng 1.000 byte → `413 Content Too Large`):

```python
from starlette.middleware.body_limit import RequestBodyLimitMiddleware
app.add_middleware(RequestBodyLimitMiddleware, max_body_size=2 * 1024 * 1024)   # 2 MB cho invoice-api
```

---

## 6. Streaming: JSONL và SSE cho `ai-gateway`

### 6.1. Vấn đề

`ai-gateway` sinh bản nháp trả lời bằng LLM trong 5–30 giây. Bắt agent CS nhìn màn hình trắng 30 giây là trải nghiệm tồi; gửi từng phần ngay khi có là chuẩn mực của các ứng dụng LLM. Từ FastAPI 0.13x, hai cơ chế được tích hợp: endpoint là **generator** → stream **JSONL**; thêm `response_class=EventSourceResponse` → stream **Server-Sent Events**.

### 6.2. JSONL

```python
from collections.abc import AsyncIterable

class DraftChunk(BaseModel):
    seq: int
    text: str

@app.get("/v1/tickets/{ticket_id}/draft.jsonl")
async def draft_jsonl(ticket_id: int) -> AsyncIterable[DraftChunk]:
    async for i, piece in llm_stream(ticket_id):          # mỗi phần tử được validate + serialize
        yield DraftChunk(seq=i, text=piece)
```

Kiểm chứng: `content-type: application/jsonl`, mỗi dòng một object JSON. OpenAPI mô tả phần tử bằng `itemSchema` trỏ tới `DraftChunk` — client sinh code biết kiểu của từng dòng.

### 6.3. SSE

```python
from fastapi.sse import EventSourceResponse, ServerSentEvent

@app.post("/v1/tickets/{ticket_id}/draft", response_class=EventSourceResponse)
async def draft_sse(ticket_id: int) -> AsyncIterable[DraftChunk]:
    async for i, piece in llm_stream(ticket_id):
        yield DraftChunk(seq=i, text=piece)                         # → "data: {...}\n\n"
    yield ServerSentEvent(event="done", data={"ok": True}, id=str(i + 1))
```

Kiểm chứng trên dây:

```text
data: {"seq":0,"text":"xin chào"}

data: {"seq":1,"text":"xin chào"}

event: done
data: {"ok": true}
id: 2
```

SSE chạy được với `POST` (khác `EventSource` của trình duyệt chỉ hỗ trợ `GET`), nên khớp với giao thức MCP stream qua `POST`. Chọn giữa hai: **SSE** khi client là trình duyệt/UI cần sự kiện có tên, `id` để nối lại (`Last-Event-ID`), `retry`; **JSONL** khi client là service khác đọc từng dòng. Module 09 tính chi phí của 60 kết nối SSE mở lâu; Module 15 bàn validate JSON từng phần của LLM.

<!-- placeholder-streaming -->

<!-- fig:streaming -->
<figure markdown="span">
  ![Stream bản nháp từ ai-gateway: mảnh đầu tiên đến sau khoảng một giây thay vì chờ cả 25 giây; định dạng SSE trên dây](assets/figures/07/streaming.light.svg#only-light){ loading=lazy }
  ![Stream bản nháp từ ai-gateway: mảnh đầu tiên đến sau khoảng một giây thay vì chờ cả 25 giây; định dạng SSE trên dây](assets/figures/07/streaming.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 7.6 — Stream bản nháp từ ai-gateway: mảnh đầu tiên đến sau khoảng một giây thay vì chờ cả 25 giây; định dạng SSE trên dây.</figcaption>
</figure>
<!-- /fig -->

---

## 7. Một request tốn bao nhiêu, và cho ai?

### 7.1. Đo trong tiến trình

Để tách chi phí của framework khỏi chi phí mạng và bộ phân tích HTTP, script `scripts/bench/bench_inside_fastapi.py` gọi thẳng ứng dụng ASGI với `receive`/`send` giả (1 core, min của 5 lần × 3.000 request):

| Endpoint | µs / request |
|---|---|
| `GET /health` → `dict` | ~54 |
| `POST /invoices` (`inv: Invoice`, 12 dòng) → `dict` | ~153 |
| `POST /invoices` → response model nhỏ | ~135 |
| `POST /invoices` → trả lại cả hóa đơn | ~149 |
| `POST /invoices` tự `model_validate_json` → response model nhỏ | **~86** |

### 7.2. Phân rã theo thư viện

cProfile trên 3.000 request `POST /invoices` (response model nhỏ), thời gian tự thân gom theo thư viện:

| Thư viện | % thời gian |
|---|---|
| FastAPI | ~28% |
| Starlette | ~21% |
| Pydantic (Python + Rust) | ~9% |
| code của bạn (handler + validator nghiệp vụ) | ~6% |
| còn lại: thư viện chuẩn (`json.loads`, `inspect`, `typing`, `email` parse content-type…) | ~35% |

<!-- placeholder-profile -->

<!-- fig:profile -->
<figure markdown="span">
  ![Số đo thật: thời gian tự thân của một request POST /invoices gom theo thư viện](assets/figures/07/profile.light.svg#only-light){ loading=lazy }
  ![Số đo thật: thời gian tự thân của một request POST /invoices gom theo thư viện](assets/figures/07/profile.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 7.7 — Số đo thật: thời gian tự thân của một request POST /invoices gom theo thư viện.</figcaption>
</figure>
<!-- /fig -->

Đọc kết quả: trong một request hóa đơn **không có database**, khung sườn (FastAPI + Starlette + thư viện chuẩn mà chúng gọi) chiếm phần lớn; phần Pydantic và code của bạn cộng lại ~15%. Khi thêm transaction DB vài mili-giây, mọi con số micro-giây ở đây trở nên nhỏ — đó là lý do Module 09–10 (đồng thời, pool, N+1) quan trọng hơn mọi tối ưu vi mô.

---

## 8. Case Mekong Cloud: `POST /v1/invoices` hoàn chỉnh (khung)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, Request, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.body_limit import RequestBodyLimitMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = Settings()            # Module 05: parse cấu hình một lần
    app.state.db = await create_pool(app.state.settings.db)   # Module 10
    yield
    await app.state.db.close()

app = FastAPI(title="Mekong Cloud invoice-api", version="1.0.0", lifespan=lifespan)
app.add_middleware(RequestBodyLimitMiddleware, max_body_size=2 * 1024 * 1024)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["https://pos.mekong.example"],
                   allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type", "Idempotency-Key"])
app.add_exception_handler(RequestValidationError, problem_422)

@app.post("/v1/invoices", status_code=status.HTTP_201_CREATED, response_model=InvoiceOut,
          responses={409: {"model": Problem}, 422: {"model": Problem}})
async def create_invoice(
    inv: InvoiceIn,                                              # Module 03–04: tầng 1–3
    idempotency_key: Annotated[UUID, Header()],                  # Module 02, 10
    tenant: Annotated[Tenant, Depends(current_tenant)],          # Module 08, 11: tầng 4
    repo: Annotated[InvoiceRepo, Depends(invoice_repo)],         # Module 10
    response: Response,
) -> InvoiceOut:
    created = await repo.create_once(tenant, idempotency_key, inv)
    response.headers["Location"] = f"/v1/invoices/{created.id}"
    return InvoiceOut.model_validate(created, from_attributes=True)
```

<!-- placeholder-case -->

<!-- fig:case -->
<figure markdown="span">
  ![Các phần của POST /v1/invoices và module phụ trách từng phần](assets/figures/07/case.light.svg#only-light){ loading=lazy }
  ![Các phần của POST /v1/invoices và module phụ trách từng phần](assets/figures/07/case.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 7.8 — Các phần của POST /v1/invoices và module phụ trách từng phần.</figcaption>
</figure>
<!-- /fig -->

Bốn module tiếp theo lần lượt điền các phần còn để trống: `current_tenant` và `invoice_repo` (Module 08), `async def` có đúng không khi driver DB là async (Module 09), `create_once` với idempotency và transaction (Module 10), xác thực và phân quyền (Module 11).

---

## Lỗi thường gặp & cách xử lý

| Triệu chứng | Nguyên nhân gốc | Cách xử lý |
|---|---|---|
| Client gửi đúng model mà vẫn 422 `["body","item"] missing` | Có hai tham số body → FastAPI bọc body theo tên | Gộp thành một model, hoặc client gửi `{"item": ..., "note": ...}` |
| Header `x_request_id` không bao giờ nhận được | Tên tham số gạch dưới, header thật gạch ngang | FastAPI tự đổi `_` → `-`; kiểm tra lại tên, hoặc `Header(alias=...)` |
| Trường nội bộ lộ ra response | Không khai báo `response_model`/kiểu trả về | Luôn khai báo model response riêng |
| 500 khi handler trả dữ liệu thiếu trường | `ResponseValidationError` | Sửa dữ liệu/ORM mapping; đó là bug thật |
| Response 422 lộ mật khẩu/token client gửi | Định dạng mặc định có `input` | Exception handler Problem Details, bỏ `input` |
| API chậm đi một nửa sau khi thêm middleware log | `@app.middleware("http")` = `BaseHTTPMiddleware` | Viết ASGI middleware thuần |
| Middleware đo thời gian không tính thời gian của CORS/nén | Thêm middleware đo trước các middleware khác | Middleware thêm sau nằm ngoài cùng — thêm đo thời gian sau cùng |
| Body thiếu `Content-Type` bị 422 | `strict_content_type=True` (chống CSRF) | Client gửi đúng header; chỉ tắt khi hiểu rủi ro |
| Payload 100 MB làm worker hết bộ nhớ | Không giới hạn body | `RequestBodyLimitMiddleware` + giới hạn ở proxy |

## Tóm tắt (cheat-sheet)

- Lúc khởi động: chữ ký hàm → `Dependant` (path/query/header/cookie/body/dependencies) + body field + response field + OpenAPI. Mỗi request chỉ đi theo cây đã dựng.
- Nguồn: tên trong path → path; kiểu đơn → query; model → body; `Header()/Cookie()/Query(model)/Body()/Form()` tường minh. Lỗi mọi nguồn gom chung, `loc[0]` = nguồn.
- Chồng ASGI: ServerError → (BodyLimit) → middleware của bạn (thêm sau = ngoài cùng) → ExceptionMiddleware → Router.
- Body: `request.json()` (`json.loads`) rồi validate; tự `model_validate_json` nhanh hơn (~135 → ~86 µs) nhưng mất OpenAPI tự động.
- `response_model`/kiểu trả về = bộ lọc an ninh + không chậm hơn `dict`; response sai → 500.
- 422 mặc định có `input` → thay bằng Problem Details (RFC 9457).
- `BaseHTTPMiddleware`: −55% throughput mỗi lớp trên `/health` (~120 µs/lớp); ASGI thuần ~0.
- Streaming tích hợp: generator → JSONL; `EventSourceResponse` → SSE, kể cả `POST`.
- Request hóa đơn trong tiến trình: FastAPI 28% · Starlette 21% · stdlib 35% · Pydantic 9% · code của bạn 6%.

## Câu hỏi tự kiểm tra / phỏng vấn

1. FastAPI làm gì lúc `@app.post(...)` được gọi, và làm gì mỗi request?

    <details markdown="1"><summary>Gợi ý</summary>
    Lúc khai báo: phân tích chữ ký → `Dependant`, dựng body/response field Pydantic, schema OpenAPI. Mỗi request: đọc body, giải dependency (validate tham số + body), gọi handler (event loop hoặc threadpool), validate/serialize response, dọn dependency yield.
    </details>

2. Cho `def f(tenant_id: int, page: int = 1, item: Item, x_trace: Annotated[str, Header()])` trên path `/t/{tenant_id}`. Mỗi tham số lấy từ đâu?

    <details markdown="1"><summary>Gợi ý</summary>
    `tenant_id` path; `page` query; `item` body; `x_trace` header `x-trace`. (Lưu ý cú pháp Python: tham số không mặc định phải đứng trước tham số có mặc định — sắp lại khi viết thật.)
    </details>

3. Vì sao trả về `dict` có thêm `tenant_id` mà response không có trường đó? Nếu bỏ `response_model` thì sao?

    <details markdown="1"><summary>Gợi ý</summary>
    `response_model` validate và dump theo model khai báo, trường không khai báo bị lọc. Bỏ đi thì `jsonable_encoder` serialize nguyên dict → lộ `tenant_id`.
    </details>

4. Khi nào FastAPI trả 422, khi nào 500 do validation?

    <details markdown="1"><summary>Gợi ý</summary>
    422: đầu vào của client không qua validate (`RequestValidationError`). 500: giá trị handler trả về không khớp response model (`ResponseValidationError`) — lỗi phía server.
    </details>

5. Hai middleware được thêm theo thứ tự A rồi B. Request đi qua thứ tự nào? Middleware đo thời gian nên thêm trước hay sau?

    <details markdown="1"><summary>Gợi ý</summary>
    B vào → A vào → app → A ra → B ra (thêm sau = ngoài cùng). Đo thời gian nên thêm sau cùng để bao trọn các middleware khác.
    </details>

6. Đồng nghiệp viết `@app.middleware("http")` để gắn request id, throughput giảm một nửa. Giải thích và sửa.

    <details markdown="1"><summary>Gợi ý</summary>
    Decorator tạo `BaseHTTPMiddleware`: chạy app bên trong trong task riêng, nối response qua stream → ~100–130 µs/lớp. Viết ASGI middleware thuần thao tác `scope`/`send` (mục 5.2) — chi phí gần 0.
    </details>

7. Vì sao định dạng 422 mặc định có thể là vấn đề bảo mật?

    <details markdown="1"><summary>Gợi ý</summary>
    Trường `input` phản chiếu lại giá trị client gửi (có thể là mật khẩu, token, số thẻ, PII); response lỗi thường bị log ở nhiều nơi. Dùng handler riêng bỏ `input`.
    </details>

8. Chọn SSE hay JSONL cho UI agent CS nhận bản nháp từ `ai-gateway`? Cho service batch đọc kết quả phân loại ticket?

    <details markdown="1"><summary>Gợi ý</summary>
    UI agent: SSE (sự kiện có tên `delta`/`done`/`error`, `id` để nối lại, trình duyệt hỗ trợ). Service batch: JSONL (đơn giản, mỗi dòng một object, dễ đọc bằng thư viện bất kỳ).
    </details>

9. Profile cho thấy Pydantic chỉ chiếm 9% thời gian một request. Bạn tối ưu gì trước?

    <details markdown="1"><summary>Gợi ý</summary>
    Bỏ `BaseHTTPMiddleware` nếu có; dùng `uvicorn[standard]`; khai báo kiểu trả về; với endpoint nóng nhất cân nhắc `model_validate_json` thủ công; sau đó nhìn sang DB và I/O (thường lớn hơn nhiều).
    </details>

## Bài tập thực hành

1. **Đọc mã nguồn (30 phút).** Mở `fastapi/routing.py`, tìm `get_request_handler` và `serialize_response`; vẽ lại sơ đồ mục 2.2 với tên hàm thật. Đánh dấu chỗ handler `def` được đẩy vào threadpool.
2. **Problem Details (CPU, 20 phút).** Cài handler mục 4.2 cho `RequestValidationError`, `HTTPException` và một ngoại lệ miền `InvoiceNumberTaken` (409). Viết test bằng `TestClient` kiểm tra `content-type` và việc không có `input`.
3. **Đo middleware (CPU, 20 phút).** Chạy `python scripts/bench/bench_concurrency.py --only e8`, rồi viết lại một middleware log của bạn bằng ASGI thuần và đo lại.
4. **SSE (CPU, 20 phút).** Viết endpoint SSE giả lập LLM (mỗi 100 ms một mẩu), dùng `curl -N` để xem stream; thêm sự kiện `error` khi LLM lỗi giữa chừng. (Lab 06 đi tiếp.)

## Tài liệu tham khảo

Tiêu chuẩn:

- RFC 9457 — *Problem Details for HTTP APIs* (2023). https://www.rfc-editor.org/rfc/rfc9457
- WHATWG HTML Living Standard — *Server-sent events*. https://html.spec.whatwg.org/multipage/server-sent-events.html
- JSON Lines. https://jsonlines.org/
- OpenAPI Specification 3.1. https://spec.openapis.org/oas/v3.1.0

Tài liệu chính thức (tra cứu 10/2026, FastAPI 0.143 / Starlette 1.8):

- FastAPI — *Tutorial*: Path/Query/Body/Header parameters, Query parameter models, Response model. https://fastapi.tiangolo.com/tutorial/
- FastAPI — *Handling Errors*. https://fastapi.tiangolo.com/tutorial/handling-errors/
- FastAPI — *Server-Sent Events*. https://fastapi.tiangolo.com/tutorial/server-sent-events/
- FastAPI — *Middleware*; *Lifespan Events*. https://fastapi.tiangolo.com/advanced/events/
- FastAPI — Release notes (SSE/JSONL, `strict_content_type`). https://fastapi.tiangolo.com/release-notes/
- Starlette — *Middleware* (BaseHTTPMiddleware và pure ASGI middleware). https://starlette.dev/middleware/
- Starlette — Release notes (1.0, `max_body_size`). https://starlette.dev/release-notes/
- Mã nguồn: `fastapi/routing.py`, `fastapi/dependencies/utils.py`, `starlette/applications.py`, `starlette/middleware/base.py`, `starlette/middleware/body_limit.py`. https://github.com/fastapi/fastapi , https://github.com/encode/starlette
