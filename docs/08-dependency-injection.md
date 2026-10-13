# Module 08 — Dependency injection

> Thời lượng: ~40 phút · Mức độ: Trung bình · Tiên quyết: Module 07

Handler `create_invoice` ở cuối Module 07 cần năm thứ không nằm trong request: cấu hình, kết nối database, tenant đang gọi (đã xác thực), repository, và một cách để test tất cả những thứ đó mà không cần database thật. Viết `settings = Settings()` hay `conn = await pool.acquire()` ngay trong handler thì chạy được, nhưng mỗi handler lặp lại cùng một đoạn, quên `release()` là rò kết nối, và test phải dựng cả hệ thống. **Dependency injection** (DI) giải quyết đúng bài toán đó. Module này đi từ lý thuyết (Fowler 2004) đến cơ chế cụ thể của FastAPI: đồ thị dependency được giải ra sao, cache trong một request, vòng đời của dependency có `yield`, và **chi phí đo được** của mỗi dependency — trong đó có một bẫy hiệu năng ít người biết.

Mọi hành vi được kiểm chứng trên FastAPI 0.143; số đo bằng `scripts/bench/bench_deps.py`.

## Mục tiêu học tập

Sau module này, bạn có thể:

1. Giải thích **Inversion of Control** và **dependency injection** (Fowler 2004), phân biệt với service locator, và nêu lợi ích cụ thể cho testability.
2. Mô tả cách FastAPI giải một **đồ thị dependency** (DAG): thứ tự topo, **cache trong một request**, và `use_cache=False`.
3. Dùng dependency có **`yield`** cho tài nguyên cần dọn dẹp; dự đoán thứ tự teardown, cách ngoại lệ truyền vào dependency, và khác biệt `scope="function"` / `scope="request"`.
4. Áp dụng các mẫu: class làm dependency, dependency có tham số, dependency cấp router/app, alias `Annotated`.
5. Định lượng chi phí: ~9 µs mỗi dependency `async def` so với ~65 µs mỗi dependency `def` (qua threadpool), và chọn đúng loại.
6. Viết test thay thế dependency bằng `dependency_overrides`.

---

## 1. Lý thuyết: IoC, DI và service locator

### 1.1. Vấn đề

```python
@app.post("/v1/invoices")
async def create_invoice(inv: InvoiceIn, request: Request):
    settings = Settings()                                   # đọc env mỗi request
    conn = await asyncpg.connect(settings.db.url)           # kết nối mới mỗi request
    token = request.headers["authorization"].removeprefix("Bearer ")
    tenant = decode_jwt(token, settings.jwt_secret)          # lặp ở mọi handler
    ...
    await conn.close()                                      # quên dòng này khi có ngoại lệ → rò kết nối
```

Handler **tự đi lấy** mọi thứ nó cần. Hậu quả: lặp code, khó đảm bảo dọn dẹp, và không thể test handler mà không có database, không có JWT thật.

### 1.2. Đảo ngược điều khiển

Martin Fowler (2004, *Inversion of Control Containers and the Dependency Injection pattern*) đặt tên cho mẫu thiết kế: thay vì đối tượng **tự tạo** hoặc **tự tìm** các đối tượng nó phụ thuộc, một thành phần bên ngoài (container/framework) **tạo và truyền vào** cho nó. Ba biến thể Fowler mô tả: *constructor injection*, *setter injection*, *interface injection*. Đối lập là **service locator**: đối tượng gọi một registry toàn cục để lấy phụ thuộc — vẫn tách được cài đặt, nhưng phụ thuộc bị **ẩn** trong thân hàm thay vì hiện trên chữ ký.

FastAPI thực hiện một dạng **"parameter injection"**: phụ thuộc được khai báo trên **chữ ký hàm** (`tenant: Annotated[Tenant, Depends(current_tenant)]`), framework gọi các hàm cung cấp và truyền kết quả vào. Ba lợi ích, mỗi cái đều kiểm chứng được:

1. **Hiện rõ**: đọc chữ ký là biết handler cần gì; OpenAPI cũng biết (dependency xác thực thêm `security` vào tài liệu).
2. **Quản lý vòng đời**: framework mở và đóng tài nguyên (mục 3), kể cả khi có ngoại lệ.
3. **Thay thế được**: test đổi `current_tenant` bằng một hàm trả tenant giả mà không sửa dòng nào của handler (mục 6).

<!-- placeholder-ioc -->

<!-- fig:ioc -->
<figure markdown="span">
  ![Handler tự lấy phụ thuộc so với được tiêm phụ thuộc qua chữ ký hàm](assets/figures/08/ioc.light.svg#only-light){ loading=lazy }
  ![Handler tự lấy phụ thuộc so với được tiêm phụ thuộc qua chữ ký hàm](assets/figures/08/ioc.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 8.1 — Handler tự lấy phụ thuộc so với được tiêm phụ thuộc qua chữ ký hàm.</figcaption>
</figure>
<!-- /fig -->

---

## 2. Đồ thị dependency

### 2.1. DAG và thứ tự giải

Dependency có thể có dependency con. Với `invoice-api`:

```python
def settings() -> Settings: ...
def db(s: Annotated[Settings, Depends(settings)]): ...                        # yield một session
def tenant(s: Annotated[Settings, Depends(settings)], conn = Depends(db)): ...
def repo(conn = Depends(db), t: Annotated[int, Depends(tenant)]): ...

@app.get("/ok")
def ok(r = Depends(repo), s = Depends(settings)): ...
```

Các quan hệ "cần" tạo thành **đồ thị có hướng không chu trình** (DAG). Khi khai báo route, FastAPI dựng cây `Dependant` (Module 07); mỗi request, `solve_dependencies` đi theo cây theo chiều sâu, giải con trước cha — tức một **thứ tự topo**. Log thật của request `/ok`:

```text
settings → db: mở → tenant → repo → handler → db: commit → db: đóng
```

<!-- placeholder-dag -->

<!-- fig:dag -->
<figure markdown="span">
  ![Đồ thị dependency của ví dụ /ok và thứ tự chạy ghi nhận được; mỗi nút chạy một lần nhờ cache trong request](assets/figures/08/dag.light.svg#only-light){ loading=lazy }
  ![Đồ thị dependency của ví dụ /ok và thứ tự chạy ghi nhận được; mỗi nút chạy một lần nhờ cache trong request](assets/figures/08/dag.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 8.2 — Đồ thị dependency của ví dụ /ok và thứ tự chạy ghi nhận được; mỗi nút chạy một lần nhờ cache trong request.</figcaption>
</figure>
<!-- /fig -->

### 2.2. Cache trong một request

`settings` được khai báo **ba lần** (bởi `db`, `tenant`, và handler) nhưng chỉ chạy **một lần**: FastAPI lưu kết quả theo khóa (hàm dependency, security scopes) trong phạm vi request, lần sau dùng lại. Tương tự `db` được `tenant` và `repo` cùng cần — cả hai nhận **cùng một** session, nên cùng một transaction. Đây không chỉ là tối ưu: nếu không có cache, `tenant` và `repo` sẽ dùng hai kết nối khác nhau và không thấy dữ liệu chưa commit của nhau.

Gọi $V$ là số dependency khác nhau, $E$ số cạnh "cần". Có cache, mỗi nút chạy đúng một lần: chi phí $O(V + E)$. Không có cache, một nút được gọi bằng **số đường đi** từ gốc tới nó — với đồ thị hình kim cương lặp lại, số đường đi tăng theo cấp số nhân. Muốn tắt cache có chủ đích (ví dụ cần hai giá trị ngẫu nhiên khác nhau): `Depends(f, use_cache=False)` — kiểm chứng: `settings` chạy hai lần.

### 2.3. Phạm vi của cache

Cache chỉ sống **trong một request**. Không có singleton xuyên request trong DI của FastAPI — muốn chia sẻ thứ đắt (pool kết nối, HTTP client, model ML) giữa các request, tạo nó trong **lifespan** (Module 07) và để dependency chỉ **lấy** nó ra:

```python
@asynccontextmanager
async def lifespan(app):
    app.state.pool = await create_pool(...)           # một lần mỗi tiến trình
    yield
    await app.state.pool.close()

def get_pool(request: Request) -> Pool:
    return request.app.state.pool                      # dependency rẻ: chỉ đọc thuộc tính
```

Hoặc dùng `functools.lru_cache` cho dependency không tham số (`settings`) — nhưng nhớ rằng nó sống suốt tiến trình và test phải `cache_clear()`.

---

## 3. Dependency có `yield`: vòng đời tài nguyên

### 3.1. Cấu trúc

```python
async def db_session(pool: Annotated[Pool, Depends(get_pool)]):
    conn = await pool.acquire()
    tx = conn.transaction()
    await tx.start()
    try:
        yield conn                         # ← handler chạy ở đây
        await tx.commit()
    except Exception:
        await tx.rollback()
        raise                              # luôn re-raise: để FastAPI trả đúng response lỗi
    finally:
        await pool.release(conn)
```

Phần trước `yield` là **setup**, giá trị `yield` được tiêm vào handler, phần sau là **teardown**. FastAPI quản lý các dependency `yield` bằng một chồng context manager (`AsyncExitStack`), nên:

- **Teardown chạy theo thứ tự ngược (LIFO)**: dependency mở sau đóng trước.
- **Ngoại lệ trong handler được ném vào dependency** tại điểm `yield`. Kiểm chứng: handler `/boom` ném `HTTPException(409)` → log `db: rollback (HTTPException) → db: đóng`, response vẫn là 409.

### 3.2. `scope`: kết thúc trước hay sau khi gửi response?

Từ các bản FastAPI gần đây, `Depends` có tham số `scope`:

- `scope="function"`: teardown chạy **sau khi handler trả về, trước khi gửi response**.
- `scope="request"` (mặc định cho dependency `yield`): teardown chạy **sau khi response đã gửi xong** — kể cả response streaming.

Thí nghiệm với một `StreamingResponse`:

```text
req: setup → fn: setup → handler → fn: teardown → stream bắt đầu → stream xong → req: teardown
```

<!-- placeholder-yield -->

<!-- fig:yield -->
<figure markdown="span">
  ![Thứ tự setup/teardown đo được của hai dependency yield với scope khác nhau quanh một response streaming](assets/figures/08/yield.light.svg#only-light){ loading=lazy }
  ![Thứ tự setup/teardown đo được của hai dependency yield với scope khác nhau quanh một response streaming](assets/figures/08/yield.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 8.3 — Thứ tự setup/teardown đo được của hai dependency yield với scope khác nhau quanh một response streaming.</figcaption>
</figure>
<!-- /fig -->

Ý nghĩa thực tế:

- Session DB cho endpoint **streaming** (SSE của `ai-gateway`, JSONL) phải có `scope="request"` nếu generator còn đọc DB trong lúc stream — nếu không, session đóng trước khi generator chạy.
- Với endpoint thường, `scope="function"` cho phép **commit trước khi trả response**: client nhận `201` thì dữ liệu chắc chắn đã ghi. Với `scope="request"`, có một khe nhỏ: response đã gửi rồi commit mới chạy — nếu commit lỗi, client đã nhận `201` cho một hóa đơn không tồn tại. Với `invoice-api`, session ghi dữ liệu dùng **`scope="function"`** (hoặc commit tường minh trong service trước khi return).

---

## 4. Các mẫu thường dùng

### 4.1. Alias bằng `Annotated`

```python
CurrentTenant = Annotated[Tenant, Depends(current_tenant)]
DbSession = Annotated[AsyncSession, Depends(db_session, scope="function")]

@app.get("/v1/invoices/{invoice_id}")
async def get_invoice(invoice_id: UUID, tenant: CurrentTenant, db: DbSession) -> InvoiceOut: ...
```

Một chỗ khai báo, mọi handler dùng lại; đổi cài đặt ở một nơi.

### 4.2. Class / instance làm dependency có tham số

```python
class RequireScope:
    """Dependency có tham số: kiểm tra token có scope yêu cầu (Module 11)."""
    def __init__(self, scope: str):
        self.scope = scope

    async def __call__(self, principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
        if self.scope not in principal.scopes:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "thiếu quyền " + self.scope)
        return principal

@app.post("/v1/invoices", dependencies=[Depends(RequireScope("invoice:write"))])
async def create_invoice(...): ...
```

Instance có `__call__` là một callable; FastAPI đọc chữ ký của `__call__`. Mỗi `RequireScope("...")` là một dependency khác nhau (khóa cache khác nhau).

### 4.3. Dependency cấp router và app

```python
admin = APIRouter(prefix="/v1/admin", dependencies=[Depends(RequireScope("admin"))])
app = FastAPI(dependencies=[Depends(enforce_tenant_header)])
```

Dependency trong `dependencies=[...]` chạy cho mọi route nhưng **không truyền giá trị** vào handler — dùng cho kiểm tra (quyền, header bắt buộc, rate limit, Module 11).

### 4.4. Dependency trả model

Dependency có thể nhận tham số query/header/body như một handler, và trả về object Pydantic — ví dụ gom tham số phân trang (`cursor`, `limit`) thành `PageParams` dùng chung cho mọi endpoint danh sách.

<!-- placeholder-patterns -->

<!-- fig:patterns -->
<figure markdown="span">
  ![Bốn mẫu dependency thường dùng](assets/figures/08/patterns.light.svg#only-light){ loading=lazy }
  ![Bốn mẫu dependency thường dùng](assets/figures/08/patterns.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 8.4 — Bốn mẫu dependency thường dùng.</figcaption>
</figure>
<!-- /fig -->

---

## 5. Chi phí: `async def` hay `def`?

### 5.1. Thí nghiệm

Một route với $k$ dependency nối tiếp nhau (mỗi cái phụ thuộc cái trước), đo trong tiến trình (min của 5 lần × 1.500 request, 1 core):

| $k$ | `async def` | `def` | `async def` + `yield` | cùng 1 dependency khai báo $k$ lần (cache) |
|---|---|---|---|---|
| 0 | 65 µs | 155 µs | 75 µs | 54 µs |
| 1 | 81 µs | 219 µs | 91 µs | 66 µs |
| 5 | 122 µs | 519 µs | 143 µs | 94 µs |
| 10 | 159 µs | 962 µs | 168 µs | 122 µs |
| 20 | 239 µs | **1.466 µs** | 375 µs | 184 µs |

<!-- placeholder-dep-cost -->

<!-- fig:dep-cost -->
<figure markdown="span">
  ![Số đo thật trong tiến trình: chi phí request theo số dependency và cách khai báo; độ dốc là chi phí mỗi dependency](assets/figures/08/dep-cost.light.svg#only-light){ loading=lazy }
  ![Số đo thật trong tiến trình: chi phí request theo số dependency và cách khai báo; độ dốc là chi phí mỗi dependency](assets/figures/08/dep-cost.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 8.5 — Số đo thật trong tiến trình: chi phí request theo số dependency và cách khai báo; độ dốc là chi phí mỗi dependency.</figcaption>
</figure>
<!-- /fig -->

Khớp đường thẳng: mỗi dependency **`async def` tốn ~9 µs**, mỗi dependency **`def` tốn ~65 µs** — gấp ~7 lần. (Ở hàng $k = 0$ cột `def` đã có một dependency `def` gốc, nên cao hơn cột `async`.)

### 5.2. Vì sao `def` đắt

Quy tắc của FastAPI cho dependency giống hệt cho handler (Module 09): `def` được chạy qua `run_in_threadpool` để không chặn event loop. Mỗi lần như vậy là một chuyến: đưa hàm sang luồng của threadpool anyio, chờ luồng chạy xong (giành GIL), báo kết quả về event loop. Với một hàm chỉ đọc một thuộc tính hay tạo một object, chuyến đi đó đắt hơn chính công việc hàng chục lần.

Quy tắc chọn:

| Dependency làm gì | Khai báo |
|---|---|
| Không I/O (đọc `request.app.state`, ghép tham số, kiểm tra scope trong token đã giải) | **`async def`** — chạy thẳng trên event loop, rẻ |
| I/O bằng thư viện async (`asyncpg`, `httpx.AsyncClient`, Redis async) | `async def` + `await` |
| I/O bằng thư viện **đồng bộ** (driver DB sync, `requests`, đọc file lớn) | `def` — chịu chi phí threadpool để không chặn loop |
| CPU nặng (băm mật khẩu Argon2 ~36 ms, Module 11) | `def` (hoặc `run_in_threadpool` tường minh) — 65 µs không đáng kể so với 36 ms, và không chặn loop |

Thêm một quan sát: khai báo cùng một dependency $k$ lần vẫn tốn ~6,5 µs mỗi lần khai báo dù hàm chỉ chạy một lần — chi phí nằm ở việc xử lý tham số và tra cache, không ở hàm.

### 5.3. Trên server thật

Thí nghiệm `e5` (Module 09 dùng chung bộ đo): `GET /deps/{k}` với chuỗi $k$ dependency `async def` qua Uvicorn (h11 + asyncio, 10 kết nối): ~3.750 request/giây với $k = 0$, ~2.360 với $k = 20$ — tức ~8 µs mỗi dependency, khớp với số đo trong tiến trình.

Với `invoice-api`, đồ thị dependency thật có ~5–6 nút → ~50 µs nếu toàn `async def`, ~350 µs nếu vô tình toàn `def`. Ở 500 request/giây, khác biệt đó là ~0,15 core CPU chỉ để nhảy qua lại threadpool.

---

## 6. Test bằng `dependency_overrides`

```python
from fastapi.testclient import TestClient

def fake_tenant() -> Tenant:
    return Tenant(id=99, tax_code="0100233488", plan="pro")

app.dependency_overrides[current_tenant] = fake_tenant
client = TestClient(app)
r = client.post("/v1/invoices", json=payload, headers={"Idempotency-Key": str(uuid4())})
app.dependency_overrides.clear()
```

Kiểm chứng trên đồ thị ở mục 2: override `tenant` bằng `lambda: 99` → log mất bước `tenant`, handler nhận `99`; các dependency còn lại (`settings`, `db`) vẫn chạy thật. Override theo **hàm gốc** làm khóa, nên phải override đúng object hàm đã dùng trong `Depends(...)` (không phải alias `Annotated`). Module 12 dựng fixture pytest cho cách làm này, kể cả session DB chạy trong một transaction rollback sau mỗi test.

<!-- placeholder-overrides -->

<!-- fig:overrides -->
<figure markdown="span">
  ![dependencyoverrides thay đúng một nút của đồ thị khi test](assets/figures/08/overrides.light.svg#only-light){ loading=lazy }
  ![dependencyoverrides thay đúng một nút của đồ thị khi test](assets/figures/08/overrides.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 8.6 — dependency_overrides thay đúng một nút của đồ thị khi test.</figcaption>
</figure>
<!-- /fig -->

---

## 7. Anti-pattern

| Anti-pattern | Vì sao hại | Thay bằng |
|---|---|---|
| Tạo pool/HTTP client **trong** dependency | mở kết nối mới mỗi request | tạo trong lifespan, dependency chỉ lấy ra |
| Dependency `def` cho việc không I/O | ~65 µs/lần qua threadpool | `async def` |
| Logic nghiệp vụ (tạo hóa đơn) nằm trong dependency | khó đọc luồng, chạy cả khi chỉ cần kiểm tra | dependency cung cấp **công cụ** (session, tenant, repo); nghiệp vụ trong service được gọi từ handler |
| Dependency `yield` nuốt ngoại lệ (không `raise`) | kiểm chứng: handler ném `HTTPException(409)` nhưng client nhận **500** — FastAPI không còn response hợp lệ để trả | luôn `raise` lại sau khi rollback |
| Session ghi dữ liệu với `scope="request"` mặc định | response 201 gửi trước khi commit | `scope="function"` hoặc commit tường minh trước `return` |
| Import module-level singleton (`db = Database()`) và dùng thẳng | không override được trong test, khởi tạo lúc import | dependency + lifespan |
| Chuỗi 15–20 dependency để "tách nhỏ" | mỗi nút vẫn tốn ~9 µs, luồng khó theo dõi | gộp các bước rẻ, giữ đồ thị nông |

---

## 8. Case Mekong Cloud: đồ thị dependency của `invoice-api`

```python
async def get_settings(request: Request) -> Settings:
    return request.app.state.settings

async def get_pool(request: Request) -> AsyncEngine:
    return request.app.state.engine

async def db_session(engine: Annotated[AsyncEngine, Depends(get_pool)]):
    async with AsyncSession(engine, expire_on_commit=False) as s:     # Module 10
        async with s.begin():                                         # commit/rollback tự động
            yield s

async def current_principal(authorization: Annotated[str, Header()],
                            s: Annotated[Settings, Depends(get_settings)]) -> Principal:
    return verify_jwt(authorization, s)                                # Module 11: JWT, RFC 8725

async def current_tenant(p: Annotated[Principal, Depends(current_principal)],
                         db: Annotated[AsyncSession, Depends(db_session, scope="function")]) -> Tenant:
    return await load_tenant(db, p.tenant_id)                          # 404 nếu tenant bị khóa

async def invoice_repo(db: Annotated[AsyncSession, Depends(db_session, scope="function")],
                       t: Annotated[Tenant, Depends(current_tenant)]) -> InvoiceRepo:
    return InvoiceRepo(db, tenant_id=t.id)                             # mọi truy vấn tự gắn tenant_id
```

<!-- placeholder-case -->

<!-- fig:case -->
<figure markdown="span">
  ![Đồ thị dependency của invoice-api](assets/figures/08/case.light.svg#only-light){ loading=lazy }
  ![Đồ thị dependency của invoice-api](assets/figures/08/case.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 8.7 — Đồ thị dependency của invoice-api.</figcaption>
</figure>
<!-- /fig -->

Ba quyết định thiết kế:

1. **Mọi dependency đều `async def`** — không cái nào chặn; ~6 nút ≈ 50 µs.
2. `current_tenant` và `invoice_repo` **dùng chung một session** nhờ cache → cùng transaction; session `scope="function"` → commit xong mới gửi `201`.
3. `InvoiceRepo` được khởi tạo **với `tenant_id`**: không có cách nào gọi repository mà quên lọc theo tenant — phòng thủ BOLA ngay trong kiểu dữ liệu (Module 10, 11).

---

## Lỗi thường gặp & cách xử lý

| Triệu chứng | Nguyên nhân gốc | Cách xử lý |
|---|---|---|
| Hai dependency thấy dữ liệu khác nhau trong cùng request | Mỗi cái tự mở session riêng thay vì cùng phụ thuộc `db_session` | Cùng phụ thuộc một dependency session (cache → một session) |
| Rò kết nối DB khi có lỗi | Dọn dẹp không nằm trong `finally`/context manager | Dependency `yield` với `try/except/finally` hoặc `async with` |
| Endpoint SSE báo session đã đóng | Session `scope="function"` kết thúc trước khi stream chạy | `scope="request"` cho dependency dùng trong generator |
| Client nhận 201 nhưng hóa đơn không có trong DB | Commit chạy sau khi response gửi (`scope="request"`) và bị lỗi | `scope="function"` cho session ghi |
| Test vẫn gọi DB thật dù đã override | Override nhầm object (alias hoặc hàm khác cùng tên) | Override đúng hàm truyền vào `Depends` |
| Latency tăng ~60 µs mỗi dependency | Dependency `def` cho việc không I/O | Đổi sang `async def` |
| Pool kết nối cạn sau vài phút | Tạo engine/pool trong dependency | Tạo trong lifespan |

## Tóm tắt (cheat-sheet)

- DI (Fowler 2004): phụ thuộc được **truyền vào**, không tự lấy; FastAPI tiêm qua chữ ký hàm → hiện rõ, quản lý vòng đời, thay thế được khi test.
- Dependency tạo DAG; giải theo thứ tự topo; **cache trong một request** theo (hàm, scopes); `use_cache=False` để tắt.
- Tài nguyên dùng chung xuyên request → lifespan; dependency chỉ lấy ra.
- `yield`: setup → handler → teardown (LIFO); ngoại lệ được ném vào dependency — rollback rồi **raise lại**.
- `scope="function"`: dọn trước khi gửi response (commit an toàn); `scope="request"` (mặc định): dọn sau response (cần cho streaming).
- Chi phí đo được: `async def` ~9 µs/dependency; `def` ~65 µs (threadpool). Không I/O → `async def`.
- Test: `app.dependency_overrides[fn] = fake`.
- `invoice-api`: settings → pool → session → principal → tenant → repo(tenant_id) — toàn `async def`, ~50 µs.

## Câu hỏi tự kiểm tra / phỏng vấn

1. Phân biệt dependency injection và service locator. FastAPI thuộc loại nào?

    <details markdown="1"><summary>Gợi ý</summary>
    DI: phụ thuộc được truyền vào từ bên ngoài, hiện trên chữ ký/constructor. Service locator: đối tượng tự gọi registry để lấy phụ thuộc, phụ thuộc ẩn trong thân hàm. FastAPI là DI qua tham số hàm (`Depends`).
    </details>

2. Một request dùng `settings` ở 3 nơi trong đồ thị. `settings` chạy mấy lần? Khi nào bạn muốn nó chạy nhiều lần?

    <details markdown="1"><summary>Gợi ý</summary>
    Một lần (cache trong request). Muốn nhiều lần khi mỗi lần phải cho giá trị mới (ví dụ sinh id ngẫu nhiên cho hai mục khác nhau) — `use_cache=False`.
    </details>

3. Viết dependency session DB đảm bảo rollback khi handler ném `HTTPException(409)`. Response client nhận được là gì?

    <details markdown="1"><summary>Gợi ý</summary>
    `try: yield s; await s.commit() except Exception: await s.rollback(); raise finally: await s.close()`. Client nhận 409 vì ngoại lệ được raise lại và ExceptionMiddleware xử lý.
    </details>

4. Vì sao session dùng trong endpoint SSE phải `scope="request"`, còn session ghi hóa đơn nên `scope="function"`?

    <details markdown="1"><summary>Gợi ý</summary>
    SSE: generator chạy sau khi handler trả về, trong lúc gửi response; teardown "function" sẽ đóng session trước đó. Ghi hóa đơn: muốn commit xong trước khi gửi 201 để không có trường hợp client nhận 201 mà commit thất bại.
    </details>

5. Một dependency chỉ đọc `request.app.state.settings` được khai báo `def`. Có vấn đề gì? Định lượng.

    <details markdown="1"><summary>Gợi ý</summary>
    Nó chạy qua threadpool: ~65 µs/lần thay vì ~9 µs với `async def` (đo trên máy của khóa). Ở 500 req/s, ~28 ms CPU mỗi giây lãng phí cho một dependency.
    </details>

6. Làm sao test `create_invoice` mà không cần JWT thật và không cần Postgres?

    <details markdown="1"><summary>Gợi ý</summary>
    `app.dependency_overrides[current_tenant] = lambda: fake_tenant`; override `db_session` bằng session tới SQLite/DB test trong transaction rollback; hoặc override `invoice_repo` bằng repo giả trong bộ nhớ (Module 12).
    </details>

7. Thiết kế dependency kiểm tra scope có tham số (`invoice:write`, `invoice:read`) dùng lại ở nhiều route.

    <details markdown="1"><summary>Gợi ý</summary>
    Class `RequireScope(scope)` có `async def __call__(self, principal = Depends(current_principal))` raise 403 khi thiếu scope; dùng `dependencies=[Depends(RequireScope("invoice:write"))]`. Hoặc `Security(current_principal, scopes=[...])` với `SecurityScopes` (Module 11).
    </details>

8. Vì sao `InvoiceRepo` nhận `tenant_id` lúc khởi tạo thay vì mỗi phương thức nhận `tenant_id` làm tham số?

    <details markdown="1"><summary>Gợi ý</summary>
    Không thể gọi phương thức nào mà quên lọc theo tenant — ràng buộc nằm trong đối tượng do DI tạo ra từ tenant đã xác thực, giảm rủi ro BOLA do sơ suất.
    </details>

## Bài tập thực hành

1. **Vẽ đồ thị (CPU, 15 phút).** Thêm `print` vào mỗi dependency của mục 8 (dùng session giả), gọi `POST /v1/invoices`, vẽ DAG và thứ tự thực thi. Đánh dấu nút nào được cache.
2. **Scope (CPU, 15 phút).** Tái tạo thí nghiệm mục 3.2 với một endpoint SSE đọc "DB" giả trong generator; quan sát lỗi khi dùng `scope="function"`.
3. **Đo chi phí (CPU, 15 phút).** Chạy `bench_deps.py` trên máy bạn; tính chi phí mỗi dependency `async def` và `def` bằng hồi quy tuyến tính.
4. **Override (CPU, 20 phút).** Viết 3 test cho `GET /v1/invoices/{id}`: tenant đúng (200), tenant khác (404), không token (401) — chỉ bằng `dependency_overrides`, không có DB thật.

## Tài liệu tham khảo

- Fowler, M. (2004). *Inversion of Control Containers and the Dependency Injection pattern*. https://martinfowler.com/articles/injection.html
- Fowler, M. (2005). *InversionOfControl*. https://martinfowler.com/bliki/InversionOfControl.html
- Seemann, M., van Deursen, S. (2019). *Dependency Injection Principles, Practices, and Patterns*. Manning — chương về service locator như anti-pattern.

Tài liệu chính thức (tra cứu 10/2026, FastAPI 0.143):

- FastAPI — *Dependencies* (sub-dependencies, caching, dependencies in path operation decorators, global dependencies). https://fastapi.tiangolo.com/tutorial/dependencies/
- FastAPI — *Dependencies with yield* (early exit và `scope`). https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/
- FastAPI — *Advanced Dependencies* (parameterized dependencies). https://fastapi.tiangolo.com/advanced/advanced-dependencies/
- FastAPI — *Testing Dependencies with Overrides*. https://fastapi.tiangolo.com/advanced/testing-dependencies/
- Python docs — `contextlib.AsyncExitStack`. https://docs.python.org/3/library/contextlib.html#contextlib.AsyncExitStack
- Mã nguồn: `fastapi/dependencies/utils.py` (`solve_dependencies`). https://github.com/fastapi/fastapi
