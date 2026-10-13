# Module 10 — Database & persistence

> Thời lượng: ~55 phút · Mức độ: Trung bình → Nâng cao · Tiên quyết: Module 08, 09

Đến Module 09, `invoice-api` mới chỉ nhận, kiểm tra và trả về hóa đơn. Một hóa đơn thật còn phải được **lưu**, được **cấp số liên tục**, không bị **tạo hai lần** khi máy POS gửi lại, không bao giờ **lộ sang tenant khác**, và schema của nó phải **đổi được** khi hệ thống đang chạy. Cả năm yêu cầu đều không giải được ở tầng Pydantic hay FastAPI. Lời giải nằm ở database: transaction, ràng buộc, khóa và pool kết nối.

Module này không dạy SQL từ đầu. Nó tập trung vào **chỗ ghép** giữa FastAPI/Pydantic và database, nơi phần lớn sự cố production xảy ra. Mỗi khẳng định đi kèm một thí nghiệm chạy thật trên **PostgreSQL 16 + SQLAlchemy 2.1 async + asyncpg**. Toàn bộ số đo nằm trong `scripts/bench/bench_db.py`, đo trên máy 4 vCPU với Postgres cùng máy, kết nối qua Unix socket.

## Mục tiêu học tập

Sau module này, bạn có thể:

1. Tổ chức tầng persistence của một service FastAPI: tách **model ORM** khỏi **schema Pydantic** (`from_attributes`), dùng **session-per-request** bằng dependency `yield`, và đặt **ranh giới transaction** đúng chỗ.
2. Chọn **kích thước pool kết nối** bằng định luật Little và Erlang C, đối chiếu với công thức HikariCP và với số đo thật (thông lượng đạt đỉnh ở pool = 2 × số core).
3. Nhận diện và sửa **N+1** cùng các anti-pattern ORM khác (Yang et al., ICSE 2018). Chọn giữa `selectinload` và `joinedload` dựa trên số đo.
4. Thiết kế **cấp số hóa đơn liên tục** và **idempotency key** chịu được request đồng thời. Giải thích bằng thí nghiệm vì sao "đọc rồi ghi" thất bại, còn ràng buộc unique và `INSERT … ON CONFLICT` thì đúng.
5. Cô lập dữ liệu **multi-tenant** bằng `tenant_id` + **Row-Level Security**, và tránh bẫy `SET` rò qua pool kết nối.
6. Lập kế hoạch **migration không downtime** theo expand/contract với Alembic, có `lock_timeout`.
7. Dùng **outbox pattern** để vừa ghi database vừa phát sự kiện mà không mất hay thừa sự kiện.

---

## 1. Kiến trúc tầng persistence

### 1.1. Ba loại "model" khác nhau

Một hóa đơn đi qua ba biểu diễn, mỗi biểu diễn có một nhiệm vụ:

| Biểu diễn | Thư viện | Nhiệm vụ | Ai được thay đổi nó |
|---|---|---|---|
| `InvoiceIn` | Pydantic | Hợp đồng **đầu vào**: kiểu, ràng buộc, quy tắc nghiệp vụ (Module 04) | đội API, theo version |
| `Invoice` (ORM) | SQLAlchemy | Ánh xạ **bảng**: khóa, quan hệ, cột nội bộ (`tenant_id`, `created_at`, `signed_xml`…) | đội backend, qua migration |
| `InvoiceOut` | Pydantic | Hợp đồng **đầu ra**: chỉ các trường được phép lộ (Module 07) | đội API, theo version |

Dùng một class cho cả ba việc là cám dỗ lớn. SQLModel được thiết kế quanh ý tưởng đó, và với CRUD nhỏ thì nó rất tiện. Nhưng ở `invoice-api`, ba biểu diễn **tiến hóa với tốc độ khác nhau**:

- Thêm một cột nội bộ không được phép làm đổi API.
- Đổi tên một trường API phải đi qua quy trình deprecation (Module 12).
- Bảng có những cột không bao giờ được trả ra ngoài: `tenant_id`, chữ ký số, ghi chú kiểm toán.

Tách ra thì tốn thêm vài chục dòng, đổi lại mỗi lớp thay đổi độc lập. Đây cũng chính là phòng tuyến chống **mass assignment** và **lộ dữ liệu** của Module 11.

<!-- placeholder-layers -->

<!-- fig:layers -->
<figure markdown="span">
  ![Ba biểu diễn của một hóa đơn: schema vào (Pydantic), model bảng (ORM), schema ra (Pydantic, fromattributes)](assets/figures/10/layers.light.svg#only-light){ loading=lazy }
  ![Ba biểu diễn của một hóa đơn: schema vào (Pydantic), model bảng (ORM), schema ra (Pydantic, fromattributes)](assets/figures/10/layers.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 10.1 — Ba biểu diễn của một hóa đơn: schema vào (Pydantic), model bảng (ORM), schema ra (Pydantic, from_attributes).</figcaption>
</figure>
<!-- /fig -->

### 1.2. Từ ORM sang Pydantic: `from_attributes`

`InvoiceOut.model_validate(orm_obj)` chỉ chạy khi model bật `from_attributes=True`. Khi đó Pydantic đọc **thuộc tính** (`getattr`) thay vì khóa dict:

```python
from pydantic import BaseModel, ConfigDict


class LineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    amount: int


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    buyer_name: str
    total: int
    lines: list[LineOut]          # đọc invoice.lines → từng LineRow → LineOut
```

Điểm quan trọng: `getattr(invoice, "lines")` trên một đối tượng ORM **có thể phát ra truy vấn SQL** (lazy load). Trong code đồng bộ, việc đó diễn ra âm thầm. Trong SQLAlchemy async, nó **không được phép**, vì không có `await` nào bao quanh `getattr`. Chạy thật trên máy đo cho ba tình huống:

```text
# 1) expire_on_commit=True (mặc định), đọc thuộc tính sau commit
MissingGreenlet: greenlet_spawn has not been called; can't call await_() here.
                 Was IO attempted in an unexpected place?

# 2) quan hệ khai báo lazy="raise", quên nạp trước
InvalidRequestError: 'Invoice.lines' is not available due to lazy='raise'

# 3) model_validate trên đối tượng đó: Pydantic gói lỗi lại
1 validation error for InvoiceOut
lines
  Error extracting attribute: InvalidRequestError: 'Invoice.lines' is not
  available due to lazy='raise' [type=get_attribute_error, ...]
```

Ba quy tắc rút ra, áp dụng cho mọi service async:

1. Tạo `async_sessionmaker(engine, expire_on_commit=False)`. Đối tượng vẫn dùng được sau `commit()` mà không phải nạp lại từ DB.
2. Khai báo quan hệ với `lazy="raise"`, hoặc bật `raiseload("*")` trong truy vấn. Thiếu eager load khi đó là **lỗi rõ ràng lúc phát triển**, không còn là truy vấn ẩn lúc chạy (xem N+1 ở mục 3).
3. Nạp đủ dữ liệu **trong** repository (`selectinload`), rồi mới đưa cho `model_validate`. Pydantic không nên là thứ kích hoạt I/O.

### 1.3. Core hay ORM?

SQLAlchemy có hai tầng. **Core** là SQL viết bằng Python (`select()`, `insert()`, `text()`), trả về `Row`. **ORM** thêm identity map, unit of work, quan hệ và lazy load. Lời khuyên thực tế cho một API:

- **ORM** cho đường đi chính, nơi bạn làm việc với "một hóa đơn và các dòng của nó". Unit of work giúp `session.add(invoice)` tự sinh đúng thứ tự `INSERT` cha trước con.
- **Core/`text()`** cho những câu mà ngữ nghĩa nằm ở SQL: `INSERT … ON CONFLICT`, `UPDATE … RETURNING`, `FOR UPDATE SKIP LOCKED`, báo cáo tổng hợp. Các mục 4–7 dùng Core vì lý do này.

Hai tầng dùng chung một `AsyncSession` và một transaction, nên trộn chúng không có vấn đề gì.

---

## 2. Session, transaction và pool kết nối

### 2.1. Session-per-request bằng dependency `yield`

Module 08 đã giới thiệu `Depends(..., scope="function")`. Đây là chỗ nó phát huy tác dụng:

```python
from typing import Annotated, AsyncIterator

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

engine = create_async_engine(
    "postgresql+asyncpg://app@db/invoices",
    pool_size=10, max_overflow=0,        # mục 2.3 giải thích con số 10
    pool_timeout=2,                      # chờ pool tối đa 2 s rồi báo lỗi (fail fast)
    pool_pre_ping=True,                  # kiểm tra kết nối chết trước khi giao
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session(tenant_id: Annotated[int, Depends(current_tenant)]) -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session, session.begin():      # mở transaction
        await session.execute(text("select set_config('app.tenant_id', :t, true)"),
                              {"t": str(tenant_id)})               # cho RLS, mục 5
        yield session
    # thoát khối: không lỗi → COMMIT; có ngoại lệ (kể cả HTTPException) → ROLLBACK


DB = Annotated[AsyncSession, Depends(get_session, scope="function")]
```

Handler thì không cần biết đến transaction:

```python
@app.post("/v1/invoices", status_code=201)
async def create_invoice(body: InvoiceIn, db: DB, tenant: CurrentTenant) -> InvoiceOut:
    inv = Invoice(tenant_id=tenant.id, buyer_name=body.buyer.name,
                  total=body.total, lines=[Line(**l.model_dump()) for l in body.lines])
    db.add(inv)
    await db.flush()                  # gửi INSERT để lấy id do DB sinh, CHƯA commit
    return InvoiceOut.model_validate(inv)
```

Chạy thật với một handler cố ý `raise HTTPException(409)` sau khi `flush()`: client nhận 409 và bảng **không có** hàng nào được thêm. Ngoại lệ đi xuyên qua `yield`, khối `session.begin()` nhận ngoại lệ và rollback.

<!-- placeholder-session -->

<!-- fig:session -->
<figure markdown="span">
  ![Session-per-request: transaction mở khi mượn kết nối và commit trước khi gửi 201 nhờ scope="function"](assets/figures/10/session.light.svg#only-light){ loading=lazy }
  ![Session-per-request: transaction mở khi mượn kết nối và commit trước khi gửi 201 nhờ scope="function"](assets/figures/10/session.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 10.2 — Session-per-request: transaction mở khi mượn kết nối và commit trước khi gửi 201 nhờ scope="function".</figcaption>
</figure>
<!-- /fig -->

Vì sao phải là `scope="function"`? Với scope mặc định `"request"`, phần sau `yield` chạy **sau khi response đã gửi đi** (Module 08 đã đo thứ tự này). Client có thể nhận `201 Created` trong khi `COMMIT` vẫn chưa chạy, và nếu commit thất bại (vi phạm ràng buộc trì hoãn, mất kết nối, failover) thì client đã tin là hóa đơn tồn tại. Với `scope="function"`, commit xong rồi response mới được gửi.

!!! warning "Không giữ transaction qua I/O chậm"
    Transaction giữ **một kết nối** và mọi **khóa** đã lấy cho tới khi kết thúc. Gọi LLM 20 s, gọi API thuế, hay stream SSE bên trong transaction sẽ giữ kết nối đó suốt thời gian ấy. Mục 2.3 cho thấy hệ quả bằng số: số kết nối cần tỉ lệ thuận với thời gian giữ. Ở `ai-gateway`, hãy đọc dữ liệu cần thiết trong một transaction ngắn, đóng nó, gọi LLM, rồi mở transaction **mới** để lưu kết quả.

### 2.2. Pool kết nối vận hành ra sao

Mở một kết nối PostgreSQL rất đắt: handshake TCP/TLS, xác thực, và **fork một tiến trình backend** phía server. Vì vậy app giữ sẵn một **pool**. `QueuePool` của SQLAlchemy có bốn tham số:

| Tham số | Ý nghĩa | Gợi ý cho API |
|---|---|---|
| `pool_size` | số kết nối giữ thường trực | tính theo mục 2.3 |
| `max_overflow` | số kết nối tạm thời được mở thêm khi pool cạn | `0`. Overflow làm tổng số kết nối khó dự đoán khi nhân với số pod |
| `pool_timeout` | thời gian chờ tối đa để mượn kết nối | 1–3 s, ngắn hơn timeout của request |
| `pool_recycle` / `pool_pre_ping` | thay kết nối cũ / kiểm tra trước khi giao | bật `pre_ping` khi có failover, proxy, NAT |

Khi pool cạn và hết `pool_timeout`, SQLAlchemy ném lỗi (chạy thật):

```text
TimeoutError: QueuePool limit of size 1 overflow 0 reached, connection timed out, timeout 0.50
```

Gặp lỗi này thì đừng vội tăng `pool_size`. Nó thường là **triệu chứng**: có transaction đang giữ kết nối quá lâu (mục 2.1), hoặc có rò kết nối (session không được đóng).

<!-- placeholder-pool -->

<!-- fig:pool -->
<figure markdown="span">
  ![Pool kết nối: request chờ mượn theo FIFO, quá pooltimeout thì lỗi; commit trả kết nối về pool](assets/figures/10/pool.light.svg#only-light){ loading=lazy }
  ![Pool kết nối: request chờ mượn theo FIFO, quá pooltimeout thì lỗi; commit trả kết nối về pool](assets/figures/10/pool.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 10.3 — Pool kết nối: request chờ mượn theo FIFO, quá pool_timeout thì lỗi; commit trả kết nối về pool.</figcaption>
</figure>
<!-- /fig -->

### 2.3. Pool cần bao nhiêu kết nối? Định luật Little

Một kết nối là một "máy phục vụ" trong mô hình hàng đợi của Module 09. Định luật Little cho số kết nối **đang bận trung bình**:

$$
L = \lambda \cdot S
$$

trong đó $\lambda$ là số transaction mỗi giây và $S$ là **thời gian giữ kết nối** của mỗi transaction (không phải thời gian request). Thí nghiệm `d8` đo $S$ cho một transaction `POST /v1/invoices` đầy đủ:

- giành idempotency key;
- ghi hóa đơn 12 dòng;
- cấp số;
- lưu response.

Kết quả: **p50 = 6,4 ms, p99 = 11,6 ms, trung bình 6,6 ms**.

Ở tải thiết kế 500 req/s:

$$
a = \lambda S = 500 \times 0{,}0066 \approx 3{,}3 \text{ kết nối bận trung bình (erlang)}
$$

Số trung bình chưa đủ, vì request đến ngẫu nhiên. Công thức Erlang C (Module 09, mục 3.4) cho xác suất một request **phải chờ** pool, $P_{\text{chờ}}$, và thời gian chờ trung bình $W_q$:

| pool $c$ | $\rho = a/c$ | $P_{\text{chờ}}$ | $W_q$ |
|---|---|---|---|
| 4 | 0,82 | 64% | 6,0 ms |
| 5 | 0,66 | 32% | 1,2 ms |
| 6 | 0,55 | 14% | 0,35 ms |
| 8 | 0,41 | 2,2% | 0,03 ms |
| 10 | 0,33 | 0,2% | ≈ 0 |

Từ bảng này, **8–10 kết nối là đủ cho 500 req/s** nếu mỗi transaction thật sự ngắn. Con số nhỏ đến bất ngờ. Ngược lại, nếu một handler giữ transaction trong lúc gọi API thuế 200 ms thì $a = 500 \times 0{,}2 = 100$, cần hơn 100 kết nối, và database sẽ gục trước khi pool kịp đủ (mục 2.4).

<!-- placeholder-little -->

<!-- fig:little -->
<figure markdown="span">
  ![Erlang C với thời gian giữ kết nối đo được: xác suất request phải chờ pool theo tải và kích thước pool](assets/figures/10/little.light.svg#only-light){ loading=lazy }
  ![Erlang C với thời gian giữ kết nối đo được: xác suất request phải chờ pool theo tải và kích thước pool](assets/figures/10/little.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 10.4 — Erlang C với thời gian giữ kết nối đo được: xác suất request phải chờ pool theo tải và kích thước pool.</figcaption>
</figure>
<!-- /fig -->

### 2.4. Nhiều kết nối hơn có nhanh hơn không? Số đo thật

Đây là câu hỏi ngược lại: phía **database**, bao nhiêu kết nối đồng thời là tối ưu? Thí nghiệm `d5` cho 64 client cùng gửi một truy vấn tốn CPU phía Postgres (~20 ms khi chạy một mình), thay đổi `pool_size`:

| pool | truy vấn/s | request p50 | request p99 | thời gian **trong DB** p50 |
|---|---|---|---|---|
| 1 | 45 | 1.389 ms | 1.752 ms | 20 ms |
| 2 | 96 | 657 ms | 815 ms | 18 ms |
| 4 | 165 | 385 ms | 729 ms | 24 ms |
| **8** | **190** | **331 ms** | **582 ms** | 37 ms |
| 16 | 171 | 369 ms | 585 ms | 84 ms |
| 32 | 171 | 366 ms | 607 ms | 162 ms |
| 64 | 161 | 377 ms | 685 ms | 284 ms |

<!-- placeholder-pool-size -->

<!-- fig:pool-size -->
<figure markdown="span">
  ![Số đo thật: thông lượng đạt đỉnh ở pool = 2 × số core; thêm kết nối chỉ chuyển hàng đợi từ app vào DB](assets/figures/10/pool-size.light.svg#only-light){ loading=lazy }
  ![Số đo thật: thông lượng đạt đỉnh ở pool = 2 × số core; thêm kết nối chỉ chuyển hàng đợi từ app vào DB](assets/figures/10/pool-size.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 10.5 — Số đo thật: thông lượng đạt đỉnh ở pool = 2 × số core; thêm kết nối chỉ chuyển hàng đợi từ app vào DB.</figcaption>
</figure>
<!-- /fig -->

Ba điều đọc ra từ bảng:

1. **Thông lượng đạt đỉnh ở pool = 8 = 2 × số core** (máy đo có 4 vCPU), rồi **giảm nhẹ**. Đây chính là quan sát đằng sau công thức trong tài liệu *About Pool Sizing* của HikariCP: `connections = (core_count × 2) + effective_spindle_count`. Với SSD, phần spindle thực tế xấp xỉ 0–1. Hệ số 2 tồn tại vì mỗi truy vấn còn có những lúc chờ I/O và mạng, nên vẫn có thêm kết nối để lấp vào. Vượt quá mức đó thì CPU chỉ còn chuyển ngữ cảnh giữa các tiến trình backend.
2. **Thêm kết nối không làm biến mất hàng đợi, chỉ dời nó đi.** Ở pool 64, request không còn chờ pool, nhưng mỗi truy vấn chạy **284 ms** trong DB thay vì 37 ms. Hàng đợi chuyển từ app (nơi bạn đo và kiểm soát được) vào bộ lập lịch của hệ điều hành trên máy DB (nơi không ai nhìn thấy). Hơn nữa, mỗi truy vấn chậm hơn thì giữ khóa lâu hơn, nên tranh chấp khóa tăng theo.
3. **Đuôi p99 tệ nhất ở hai đầu**: pool 1 do xếp hàng, pool 64 do tranh CPU. Vùng tốt nằm quanh 2 × core.

Cần đọc số đo này cẩn thận. Client Python chạy chung 4 vCPU với Postgres, nên điểm đỉnh trên máy riêng có thể khác đôi chút. Hình dạng đường cong (tăng, đạt đỉnh, rồi giảm) mới là kết luận chuyển được sang máy khác.

!!! example "Case thực tế — `invoice-api` của Mekong Cloud"
    Database: Postgres 8 vCPU, trần **tổng** kết nối hợp lý khoảng 2 × 8 + 1 ≈ 17–20 kết nối **đang chạy truy vấn**. App: 4 pod × 1 tiến trình Uvicorn (Module 13), mỗi pool `pool_size=5, max_overflow=0`, tổng 20 kết nối. Theo Erlang C, 4 pool × 5 kết nối ở 125 req/s/pod cho $a = 0{,}83$ mỗi pod, $P_{\text{chờ}} < 1\%$.

    Khi cần 20 pod (autoscale ngày cuối tháng), $20 \times 5 = 100$ kết nối sẽ vượt mức tối ưu. Lúc đó đặt **PgBouncer** ở chế độ transaction pooling giữa app và DB: 100 kết nối phía client dồn vào ~20 kết nối thật. Lưu ý asyncpg dùng prepared statement. Sau PgBouncer ở chế độ transaction, cần cấu hình PgBouncer ≥ 1.21 với `max_prepared_statements`, hoặc tắt cache prepared statement của asyncpg (`prepared_statement_cache_size=0` trong URL của SQLAlchemy).

---

## 3. N+1 và các anti-pattern ORM

### 3.1. Vấn đề

Endpoint `GET /v1/invoices?limit=200` trả về hóa đơn kèm dòng hàng. Đoạn code ngây thơ sau đây trông vô hại:

```python
invoices = (await db.scalars(select(Invoice).limit(200))).all()     # 1 truy vấn
for inv in invoices:
    lines = (await db.scalars(select(Line).where(Line.invoice_id == inv.id))).all()   # +1 mỗi hóa đơn
```

Đây là **N+1**: một truy vấn danh sách cộng thêm N truy vấn con. Mỗi truy vấn con rất nhanh, nhưng mỗi cái tốn một **vòng khứ hồi** (round trip): gửi, Postgres lập kế hoạch và thực thi, gửi về, driver giải mã.

### 3.2. Số đo thật

Thí nghiệm `d1`: 200 hóa đơn × 12 dòng, Postgres cùng máy (Unix socket, round trip ~0,5 ms).

| Chiến lược | 10 hóa đơn | 50 hóa đơn | 200 hóa đơn | Số truy vấn (200) |
|---|---|---|---|---|
| N+1 | 10,9 ms | 31,1 ms | **122,4 ms** | 201 |
| `selectinload` | 2,9 ms | 4,8 ms | **17,5 ms** | 2 |
| `joinedload` | 1,9 ms | 6,9 ms | 22,6 ms | 1 |

<!-- placeholder-nplus1 -->

<!-- fig:nplus1 -->
<figure markdown="span">
  ![Số đo thật: N+1 tăng tuyến tính theo số round trip; selectinload và joinedload giữ số truy vấn cố định](assets/figures/10/nplus1.light.svg#only-light){ loading=lazy }
  ![Số đo thật: N+1 tăng tuyến tính theo số round trip; selectinload và joinedload giữ số truy vấn cố định](assets/figures/10/nplus1.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 10.6 — Số đo thật: N+1 tăng tuyến tính theo số round trip; selectinload và joinedload giữ số truy vấn cố định.</figcaption>
</figure>
<!-- /fig -->

Thời gian N+1 tăng **tuyến tính theo số round trip**: khoảng 0,6 ms mỗi hóa đơn. Con số đó là trên Unix socket. Qua mạng trong cùng datacenter (RTT 0,3–1 ms) cộng thêm 60–200 ms. Còn nếu DB nằm khác vùng (RTT 30 ms) thì 200 hóa đơn mất **6 giây**. N+1 vô hình ở môi trường dev, nơi DB nằm ngay trên laptop, và chỉ lộ ra ở production.

### 3.3. `selectinload` hay `joinedload`?

| | `selectinload` | `joinedload` |
|---|---|---|
| SQL | `SELECT … FROM invoices` rồi `SELECT … FROM lines WHERE invoice_id IN (…)` | một `SELECT … FROM invoices LEFT JOIN lines` |
| Số truy vấn | 2 (mỗi quan hệ thêm 1) | 1 |
| Dữ liệu trả về | mỗi hóa đơn 1 lần | cột hóa đơn **lặp lại 12 lần** (mỗi dòng hàng) |
| Tốt khi | quan hệ **một-nhiều**, nhiều con | quan hệ **nhiều-một** / một-một (ví dụ `line.product`) |
| Số đo (200 HĐ) | 17,5 ms | 22,6 ms |

`joinedload` thắng ở n nhỏ vì nó tiết kiệm một round trip. Khi n lớn, nó thua vì phải truyền và giải mã 2.400 hàng chứa dữ liệu hóa đơn lặp lại. Quy tắc mặc định của tài liệu SQLAlchemy cũng như vậy: `selectinload` cho collection, `joinedload` cho quan hệ nhiều-một.

### 3.4. Nghiên cứu: anti-pattern ORM ngoài thực tế

Yang và cộng sự (**ICSE 2018**, *"How not to structure your database-backed web applications: a study of performance bugs in the wild"*) khảo sát 12 ứng dụng Rails mã nguồn mở phổ biến và tổng kết **9 anti-pattern hiệu năng ORM** từ hơn 200 vấn đề hiệu năng. Sau khi sửa tay 64 lỗi, họ đạt mức tăng tốc trung vị **2×** (tối đa 39×), phần lớn chỉ với **dưới 5 dòng code**. Trước đó, Chen và cộng sự (**ICSE 2014**) đã chỉ ra các anti-pattern truy cập dữ liệu qua ORM (ví dụ truy vấn thừa trong vòng lặp) và xây công cụ phát hiện tự động.

Các anti-pattern thường gặp nhất, ánh xạ sang SQLAlchemy:

| Anti-pattern | Dạng trong SQLAlchemy | Cách sửa |
|---|---|---|
| Truy vấn trong vòng lặp (N+1) | lazy load trong `for` | `selectinload`, `lazy="raise"` |
| Nạp cột không dùng | `select(Invoice)` khi chỉ cần `id, total` | `select(Invoice.id, Invoice.total)`, `load_only()`, `defer()` cho cột lớn như `signed_xml` |
| Đếm bằng cách nạp hết | `len((await db.scalars(q)).all())` | `select(func.count()).select_from(...)` |
| Phân trang bằng `OFFSET` lớn | `.offset(100_000)` | phân trang theo con trỏ (keyset, Module 02) |
| Lọc trong Python | nạp hết rồi `[x for x in rows if ...]` | đẩy điều kiện vào `WHERE` |
| Thiếu index cho truy vấn thường dùng | `WHERE tenant_id = ? ORDER BY issued_at` | index `(tenant_id, issued_at)` |

Cách phát hiện trong dự án: bật `lazy="raise"` toàn cục, đếm truy vấn mỗi request trong test (dùng sự kiện `before_cursor_execute`, như `bench_db.py` làm), và đặt ngưỡng trong CI, ví dụ "`GET /v1/invoices` ≤ 3 truy vấn".

---

## 4. Cấp số hóa đơn: race condition trong một dòng SQL

### 4.1. Yêu cầu

Theo Nghị định 123/2020/NĐ-CP (khoản 3 Điều 10), số hóa đơn có **tối đa 8 chữ số**, lập **theo thứ tự liên tục từ nhỏ đến lớn** trong cùng một ký hiệu hóa đơn, và bắt đầu lại từ 1 mỗi năm. Như vậy hai yêu cầu kỹ thuật là: **không trùng** và **không nhảy số**.

### 4.2. Thí nghiệm: ba cách, 400 giao dịch, 32 đồng thời

```python
# Cách 1 — MAX()+1: đọc rồi ghi
nxt = await s.scalar(text("select coalesce(max(number),0)+1 from inv_numbers where series='1C26TMK'"))
await s.execute(text("insert into inv_numbers(series, number) values ('1C26TMK', :n)"), {"n": nxt})

# Cách 2 — bộ đếm theo ký hiệu, khóa hàng bằng UPDATE … RETURNING
nxt = await s.scalar(text("update series_counter set last_number = last_number + 1 "
                          "where series='1C26TMK' returning last_number"))

# Cách 3 — SEQUENCE của Postgres
nxt = await s.scalar(text("select nextval('inv_seq')"))
```

Kết quả (thí nghiệm `d2`):

| Cách | Số hàng | **Trùng số** | **Khoảng trống** | Giao dịch/s |
|---|---|---|---|---|
| `MAX()+1` | 400 | **371** | 0 | 846 |
| `UPDATE … RETURNING` (khóa hàng) | 400 | 0 | 0 | 438 |
| `sequence` | 400 | 0 | 0 | 948 |
| `sequence` + 5% giao dịch rollback | 380 | 0 | **19** | 1.131 |

<!-- placeholder-numbering -->

<!-- fig:numbering -->
<figure markdown="span">
  ![Số đo thật: ba cách cấp số hóa đơn dưới 32 giao dịch đồng thời — đúng đắn và thông lượng](assets/figures/10/numbering.light.svg#only-light){ loading=lazy }
  ![Số đo thật: ba cách cấp số hóa đơn dưới 32 giao dịch đồng thời — đúng đắn và thông lượng](assets/figures/10/numbering.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 10.7 — Số đo thật: ba cách cấp số hóa đơn dưới 32 giao dịch đồng thời — đúng đắn và thông lượng.</figcaption>
</figure>
<!-- /fig -->

**`MAX()+1` sai gần như hoàn toàn**: 400 hóa đơn chỉ có 29 số khác nhau. Ở mức cô lập mặc định **READ COMMITTED**, 32 transaction cùng đọc `MAX` khi chưa ai commit, nên cùng thấy một giá trị và cùng ghi `MAX+1`. Một `asyncio.sleep(0)` giữa đọc và ghi là đủ để race xảy ra. Code thật còn có validate, tính thuế, ký số ở khoảng giữa đó.

**Sequence không trùng nhưng nhảy số**. `nextval()` được thiết kế **không transactional**: số đã cấp không được trả lại khi transaction rollback. Điều này cố ý, để sequence không bao giờ phải khóa. Hệ quả là 19 khoảng trống ứng với 19 giao dịch bị hủy. Với khóa chính thì khoảng trống không sao, nhưng **với số hóa đơn thì vi phạm yêu cầu liên tục**.

**Bộ đếm có khóa hàng đúng cả hai yêu cầu**. `UPDATE` lấy khóa ghi trên hàng `series_counter`, nên transaction thứ hai **chờ** tới khi transaction thứ nhất commit hoặc rollback. Nếu transaction thứ nhất rollback, giá trị `last_number` cũng được rollback, nên không có khoảng trống. Cái giá là mọi giao dịch cùng ký hiệu bị **tuần tự hóa**: thông lượng giảm một nửa (438 so với 948/s).

### 4.3. Trần thông lượng của một khóa: lại là Little

Khóa trên một ký hiệu là một máy phục vụ **duy nhất**, và thời gian phục vụ của nó là **thời gian từ lúc lấy khóa tới lúc commit**. Từ đó:

$$
X_{\max}(\text{một ký hiệu}) = \frac{1}{t_{\text{giữ khóa}}}
$$

438 giao dịch/s tương ứng thời gian giữ khóa ≈ 2,3 ms. Hai hệ quả thiết kế:

1. **Lấy số càng muộn càng tốt trong transaction**. Validate, tính tiền, ghi dòng hàng trước, rồi cấp số **ngay trước commit**, như thí nghiệm `d8` làm. Nếu cấp số ở đầu transaction rồi làm thêm 6 ms việc khác, trần giảm còn ~150/s.
2. **Khóa theo ký hiệu, không khóa toàn cục**. Mỗi tenant có ký hiệu riêng, và 3.000 tenant song song không tranh nhau. Một tenant rất lớn (chuỗi siêu thị) có thể tạo nhiều ký hiệu theo cửa hàng. Đây là thiết kế được pháp luật cho phép.

Cuối cùng, luôn thêm ràng buộc `UNIQUE (tenant_id, series, number)` làm **phòng tuyến cuối**. Nếu một bug nào đó đi vòng qua bộ đếm, database sẽ từ chối thay vì lặng lẽ lưu hai hóa đơn trùng số.

---

## 5. Idempotency key: không tạo hóa đơn hai lần

### 5.1. Bài toán

Máy POS gửi `POST /v1/invoices` và mạng chập chờn: request tới server, hóa đơn được tạo, nhưng response bị mất. POS gửi lại. Nếu server tạo hóa đơn thứ hai thì khách hàng có hai hóa đơn cho một lần mua. Module 02 đã nêu lời giải ở tầng HTTP: client gửi header **`Idempotency-Key`** (UUID sinh một lần cho mỗi giao dịch), và server đảm bảo **cùng khóa thì cùng kết quả**. IETF đã soạn Internet-Draft *The Idempotency-Key HTTP Header Field* (nhóm httpapi) cho header này. Bản cuối là -07 (10/2025); tính đến 10/2026, draft đã hết hạn và chưa thành RFC. Tuy vậy, nó vẫn là mô tả tham chiếu tốt nhất, và các API thanh toán như Stripe đã dùng header này từ lâu. Draft khuyến nghị: thiếu khóa ở endpoint bắt buộc → `400`; dùng lại khóa với payload khác → `422`; bản gốc còn đang xử lý → `409`.

Phần khó là phía server: **50 request trùng khóa đến cùng lúc**. Đây không phải giả định cực đoan. POS retry với timeout ngắn, cộng với load balancer retry, rất dễ tạo ra vài bản sao gần như đồng thời.

### 5.2. Thí nghiệm: ba thiết kế

Thí nghiệm `d3`: 50 request đồng thời cùng một khóa, mỗi request có 2 ms "xử lý nghiệp vụ", lặp 20 lần.

| Thiết kế | Hóa đơn tạo ra cho **một** khóa | Kết cục trung bình của 50 request |
|---|---|---|
| `SELECT` khóa → nếu chưa có thì `INSERT`, **không** ràng buộc unique | **39,7** | 39,7 tạo mới, 10,3 phát lại |
| `SELECT` → `INSERT`, có `PRIMARY KEY (tenant_id, key)` | 1 | 1 tạo mới, **39 lỗi 500**, 10 phát lại |
| `INSERT … ON CONFLICT DO NOTHING` **trước**, rồi mới xử lý | **1** | 1 tạo mới, **49 phát lại** |

<!-- placeholder-idem -->

<!-- fig:idem -->
<figure markdown="span">
  ![Idempotency key: kiểm tra-rồi-ghi để lọt race, giành khóa trước bằng ON CONFLICT thì không; kết cục đo được của 50 request trùng](assets/figures/10/idem.light.svg#only-light){ loading=lazy }
  ![Idempotency key: kiểm tra-rồi-ghi để lọt race, giành khóa trước bằng ON CONFLICT thì không; kết cục đo được của 50 request trùng](assets/figures/10/idem.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 10.8 — Idempotency key: kiểm tra-rồi-ghi để lọt race, giành khóa trước bằng ON CONFLICT thì không; kết cục đo được của 50 request trùng.</figcaption>
</figure>
<!-- /fig -->

- Thiết kế 1 là cùng lỗi "đọc rồi ghi" của mục 4: mọi request cùng `SELECT` khi chưa ai commit, và tất cả đều kết luận "chưa có".
- Thiết kế 2 **đúng về dữ liệu** nhờ ràng buộc unique: transaction thứ hai trở đi vi phạm khóa chính và **rollback toàn bộ**, kể cả hóa đơn của nó. Nhưng client nhận 500 cho một request hoàn toàn hợp lệ, sẽ retry, rồi mới được phát lại. Đúng nhưng ồn, và log đầy lỗi giả.
- Thiết kế 3 **giành khóa trước khi làm việc**. Tính đúng đắn đến từ cách Postgres xử lý `INSERT … ON CONFLICT` khi có một transaction khác vừa chèn cùng khóa nhưng **chưa commit**: lệnh `INSERT` thứ hai **chờ** transaction thứ nhất kết thúc. Nếu transaction thứ nhất commit, lệnh thứ hai thấy xung đột, `DO NOTHING`, và đọc được response đã lưu. Nếu transaction thứ nhất rollback, lệnh thứ hai chèn thành công và trở thành người xử lý. Không có cửa sổ nào để hai request cùng tạo hóa đơn.

### 5.3. Cài đặt đầy đủ

```python
import hashlib, json
from typing import Annotated
from uuid import UUID

from fastapi import Header
from fastapi.responses import JSONResponse
from sqlalchemy import text

# create table idempotency_keys (
#   tenant_id int not null, key uuid not null, request_hash text not null,
#   status_code int, response_body jsonb, created_at timestamptz not null default now(),
#   primary key (tenant_id, key));


@app.post("/v1/invoices", status_code=201)
async def create_invoice(body: InvoiceIn, db: DB, tenant: CurrentTenant,
                         idempotency_key: Annotated[UUID, Header()]):
    req_hash = hashlib.sha256(body.model_dump_json().encode()).hexdigest()   # băm model ĐÃ validate
    claimed = await db.scalar(text(
        "insert into idempotency_keys(tenant_id, key, request_hash) values (:t, :k, :h) "
        "on conflict (tenant_id, key) do nothing returning key"),
        {"t": tenant.id, "k": idempotency_key, "h": req_hash})
    if claimed is None:                                   # khóa đã có chủ và chủ đã commit
        row = (await db.execute(text(
            "select request_hash, status_code, response_body from idempotency_keys "
            "where tenant_id = :t and key = :k"), {"t": tenant.id, "k": idempotency_key})).one()
        if row.request_hash != req_hash:
            return JSONResponse({"title": "Idempotency-Key đã dùng cho payload khác"}, status_code=422)
        return JSONResponse(row.response_body, status_code=row.status_code,
                            headers={"Idempotent-Replayed": "true"})
    out = await invoice_service.create(db, tenant, body)  # validate nghiệp vụ, cấp số, ghi hóa đơn
    payload = out.model_dump(mode="json")
    await db.execute(text(
        "update idempotency_keys set status_code = 201, response_body = cast(:b as jsonb) "
        "where tenant_id = :t and key = :k"), {"b": json.dumps(payload), "t": tenant.id, "k": idempotency_key})
    return payload                                        # hóa đơn + response đã lưu commit CÙNG LÚC
```

Chạy thật với 20 request đồng thời cùng khóa: **1** response `201`, **19** response `201` kèm `Idempotent-Replayed: true`, cùng `id`, và bảng có đúng 1 hóa đơn. Hai chi tiết đáng chú ý:

- **Băm model đã validate, không băm bytes thô.** Gửi lại cùng hóa đơn nhưng đổi thứ tự khóa JSON và khoảng trắng vẫn được nhận là cùng request (đã chạy thử: phát lại 201). Lý do: `model_dump_json()` luôn xuất các trường theo thứ tự khai báo trong model. Đổi một số tiền thì hash khác, nên server trả **422**, đúng như Internet-Draft khuyến nghị cho việc dùng lại khóa với payload khác.
- **Khóa và kết quả nằm trong cùng transaction với hóa đơn.** Nếu xử lý thất bại, cả khóa cũng rollback, và client retry được bằng chính khóa đó. Không bao giờ tồn tại trạng thái "đã giữ khóa nhưng không có hóa đơn".

### 5.4. Trade-off và vòng đời khóa

Thiết kế 3 có một cái giá: 49 request trùng **chờ** trong Postgres, mỗi request **giữ một kết nối** trong lúc chờ. Với 2–3 bản sao thì không vấn đề gì. Nếu kịch bản retry có thể tạo hàng chục bản sao, có một biến thể khác:

1. Giành khóa trong một **transaction riêng, commit ngay**, với cột `status = 'processing'`.
2. Bản sao đến sau thấy `processing` → trả ngay **`409 Conflict`** kèm `Retry-After` (Internet-Draft gợi ý 409 cho request trùng khi bản gốc còn đang xử lý).
3. Xử lý xong thì cập nhật `status = 'completed'` + response.

Biến thể này không giữ kết nối, nhưng phải xử lý thêm trường hợp tiến trình chết giữa bước 1 và 3: khóa kẹt ở `processing`. Cách xử lý là thêm hạn `locked_until`, hoặc chia "điểm khôi phục" (recovery point) như bài viết của Brandur Leach về idempotency key kiểu Stripe trên Postgres.

Dọn dẹp: khóa không cần sống mãi. Stripe giữ khóa 24 giờ. Với `invoice-api`, POS retry trong vòng vài phút, nên giữ 48 giờ là đủ. Xóa theo lô bằng job định kỳ, hoặc chia partition theo ngày và `DROP PARTITION`.

---

## 6. Multi-tenant: `tenant_id` và Row-Level Security

### 6.1. Ba mô hình

| Mô hình | Cô lập | Chi phí vận hành với 3.000 tenant | Khi nào dùng |
|---|---|---|---|
| DB riêng mỗi tenant | mạnh nhất | 3.000 DB, 3.000 lần migration | ít tenant lớn, yêu cầu pháp lý riêng |
| Schema riêng mỗi tenant | trung bình | 3.000 schema, catalog phình to | vài chục–vài trăm tenant |
| **Bảng chung + cột `tenant_id`** | phụ thuộc code | một schema, một migration | **nhiều tenant nhỏ, như `invoice-api`** |

Bảng chung là lựa chọn hợp lý cho 3.000 tenant, nhưng có một rủi ro: **chỉ cần quên một `WHERE tenant_id = …`** là lộ hóa đơn của tenant khác. Đây chính là lỗ hổng **BOLA**, mục số 1 trong OWASP API Top 10 (Module 11).

### 6.2. Row-Level Security: để database nhớ thay bạn

PostgreSQL cho phép gắn **policy** vào bảng. Mọi truy vấn của role không được miễn trừ đều bị **tự động thêm điều kiện**:

```sql
alter table invoices enable row level security;
create policy tenant_isolation on invoices
  using (tenant_id = current_setting('app.tenant_id')::int);
```

App đặt tenant cho mỗi transaction (dependency ở mục 2.1). Thí nghiệm `d4` có 30 hóa đơn chia đều cho 3 tenant. Chạy **cùng một câu `select count(*) from invoices` không có `WHERE`**:

```text
tenant 1: thấy 10 hàng, tenant_id xuất hiện: [1]
tenant 2: thấy 10 hàng, tenant_id xuất hiện: [2]
```

<!-- placeholder-rls -->

<!-- fig:rls -->
<figure markdown="span">
  ![Row-Level Security: cùng một truy vấn không WHERE, mỗi tenant chỉ thấy hàng của mình](assets/figures/10/rls.light.svg#only-light){ loading=lazy }
  ![Row-Level Security: cùng một truy vấn không WHERE, mỗi tenant chỉ thấy hàng của mình](assets/figures/10/rls.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 10.9 — Row-Level Security: cùng một truy vấn không WHERE, mỗi tenant chỉ thấy hàng của mình.</figcaption>
</figure>
<!-- /fig -->

Ba điểm vận hành quan trọng, tất cả đều dễ bị bỏ qua:

1. **Chủ bảng và superuser bỏ qua RLS.** Role tạo bảng (thường là role chạy migration) không bị policy ràng buộc, trừ khi bật `ALTER TABLE … FORCE ROW LEVEL SECURITY`. Superuser và role có `BYPASSRLS` luôn bỏ qua. App phải kết nối bằng một role **riêng**, không sở hữu bảng. Thí nghiệm dùng `set local role app_user` vì lý do này.
2. **Phải là `SET LOCAL` (`set_config(..., true)`), không phải `SET`.** Đây là bẫy nguy hiểm nhất, và thí nghiệm `d4leak` cho thấy nó trực tiếp. Dùng pool 1 kết nối: request 1 đặt tenant 1 rồi trả kết nối; request 2 **quên** đặt tenant.

    | Request 1 dùng | Request 2 thấy `app.tenant_id` | Request 2 đọc được |
    |---|---|---|
    | `set_config(..., false)` ~ `SET` | `'1'` | **10 hàng của tenant 1** |
    | `set_config(..., true)` ~ `SET LOCAL` | `''` | lỗi `invalid input syntax for type integer: ""` |

    `SET` cấp session **sống cùng kết nối**, mà kết nối được pool trả cho request khác, nên dữ liệu của tenant 1 lộ sang request 2. `SET LOCAL` hết hiệu lực khi transaction kết thúc, nên request quên đặt tenant sẽ **thất bại an toàn** (fail closed) thay vì thấy dữ liệu của người khác.

3. **RLS là lưới an toàn, không thay cho `WHERE tenant_id`.** Vẫn viết điều kiện tenant trong truy vấn, để planner dùng được index `(tenant_id, …)` và để code đọc lên là hiểu. RLS bảo vệ bạn khỏi lần **quên** duy nhất.

Về hiệu năng: policy chỉ là một điều kiện thêm vào `WHERE`. Nếu có index bắt đầu bằng `tenant_id` thì chi phí không đáng kể. Cẩn thận với policy gọi hàm phức tạp hoặc subquery cho mỗi hàng.

---

## 7. Migration không downtime: expand/contract

### 7.1. Vì sao migration làm sập API: hàng đợi khóa

`ALTER TABLE … ADD COLUMN` trên Postgres hiện đại (từ bản 11, kể cả có `DEFAULT` hằng) chỉ sửa catalog, chạy trong vài mili giây. Vậy tại sao migration kiểu này vẫn làm sập API? Thí nghiệm `d6` tái hiện:

1. Một transaction "báo cáo" đọc bảng `invoices` và chạy **2 giây**. Nó giữ khóa `ACCESS SHARE`.
2. Migration chạy `ALTER TABLE invoices ADD COLUMN note text`. Lệnh cần khóa `ACCESS EXCLUSIVE`, nên phải **chờ** báo cáo xong.
3. API tiếp tục gửi `SELECT` vào `invoices` mỗi 100 ms. Mỗi request độc lập với nhau, như traffic thật.

| Migration | ALTER | `SELECT` chậm nhất của API |
|---|---|---|
| không `lock_timeout` | chờ 1,8 s rồi thành công | **1.718 ms**; 18 request liên tiếp bị chặn |
| `SET LOCAL lock_timeout = '100ms'` | thất bại sau 104 ms (`canceling statement due to lock timeout`) | **4,2 ms** |

<!-- placeholder-lockqueue -->

<!-- fig:lockqueue -->
<figure markdown="span">
  ![Số đo thật: ALTER TABLE chờ khóa sau transaction dài chặn mọi SELECT đến sau nó; locktimeout loại bỏ hoàn toàn hiện tượng này](assets/figures/10/lockqueue.light.svg#only-light){ loading=lazy }
  ![Số đo thật: ALTER TABLE chờ khóa sau transaction dài chặn mọi SELECT đến sau nó; locktimeout loại bỏ hoàn toàn hiện tượng này](assets/figures/10/lockqueue.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 10.10 — Số đo thật: ALTER TABLE chờ khóa sau transaction dài chặn mọi SELECT đến sau nó; lock_timeout loại bỏ hoàn toàn hiện tượng này.</figcaption>
</figure>
<!-- /fig -->

Cơ chế: khóa trong Postgres được cấp **theo hàng đợi FIFO**. `ACCESS EXCLUSIVE` đang chờ sẽ chặn mọi yêu cầu khóa đến sau nó, kể cả `ACCESS SHARE` vốn tương thích với báo cáo đang chạy. Vì vậy một lệnh DDL "tức thời" đứng chờ sau một truy vấn dài sẽ **chặn toàn bộ truy vấn của API**. Pool cạn, mọi request timeout. Với `lock_timeout`, migration tự hủy và chạy lại sau. API không hề biết có chuyện gì.

### 7.2. Expand/contract (parallel change)

Thay đổi không tương thích ngược, như đổi tên `buyer_name` → `legal_name`, không thể làm trong một bước. Lý do: trong lúc rolling deploy, **phiên bản app cũ và mới chạy cùng lúc** trên cùng một database. Mẫu **expand/contract** (Danilo Sato, *Parallel Change*, martinfowler.com, 2014) chia thay đổi thành các bước, và mỗi bước tương thích với cả hai phiên bản app liền kề:

| Bước | Database | App | Tương thích |
|---|---|---|---|
| 1. Expand | thêm cột `legal_name` **nullable** | — | app cũ không biết cột mới, không sao |
| 2. Dual write | — | ghi **cả hai** cột, đọc cột cũ | app cũ vẫn chạy |
| 3. Backfill | chép dữ liệu cũ sang theo **lô nhỏ** | — | — |
| 4. Chuyển đọc | — | đọc `legal_name`, vẫn ghi cả hai | rollback app vẫn an toàn |
| 5. Ngừng ghi cột cũ | — | chỉ dùng `legal_name` | — |
| 6. Contract | `NOT NULL`, xóa `buyer_name` | — | chỉ khi **không còn** phiên bản nào dùng cột cũ |

<!-- placeholder-expand -->

<!-- fig:expand -->
<figure markdown="span">
  ![Expand/contract: đổi tên cột qua sáu bước, mỗi bước tương thích với phiên bản app liền kề](assets/figures/10/expand.light.svg#only-light){ loading=lazy }
  ![Expand/contract: đổi tên cột qua sáu bước, mỗi bước tương thích với phiên bản app liền kề](assets/figures/10/expand.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 10.11 — Expand/contract: đổi tên cột qua sáu bước, mỗi bước tương thích với phiên bản app liền kề.</figcaption>
</figure>
<!-- /fig -->

Ba migration Alembic tương ứng (đã chạy thật trên Postgres với 5.000 hàng):

```python
# versions/0001_expand.py
def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")             # không xếp hàng vô hạn sau transaction dài
    op.add_column("buyers", sa.Column("legal_name", sa.Text(), nullable=True))

# versions/0002_backfill.py
def upgrade() -> None:
    with op.get_context().autocommit_block():               # mỗi lô một transaction ngắn
        while True:
            n = op.get_bind().exec_driver_sql(
                "UPDATE buyers SET legal_name = buyer_name WHERE id IN ("
                "  SELECT id FROM buyers WHERE legal_name IS NULL LIMIT 1000)").rowcount
            if n == 0:
                break

# versions/0003_contract.py — chạy ở một lần deploy SAU
def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.alter_column("buyers", "legal_name", nullable=False)
    op.drop_column("buyers", "buyer_name")
```

Phía API, Pydantic hỗ trợ giai đoạn chuyển tiếp. Ta nhận cả tên cũ lẫn tên mới, nhưng chỉ công bố tên mới trong schema:

```python
from pydantic import AliasChoices, BaseModel, Field


class BuyerIn(BaseModel):
    legal_name: str = Field(validation_alias=AliasChoices("legal_name", "buyer_name"))

BuyerIn.model_validate({"buyer_name": "Cty A"})    # legal_name='Cty A'  (client cũ)
BuyerIn.model_validate({"legal_name": "Cty B"})    # legal_name='Cty B'  (client mới)
# JSON Schema chỉ liệt kê legal_name → client mới sinh từ OpenAPI dùng tên mới
```

Thêm vài quy tắc vận hành:

- Tạo index bằng `CREATE INDEX CONCURRENTLY`. Lệnh này không được chạy trong transaction, nên trong Alembic phải dùng `autocommit_block()`.
- Thêm ràng buộc bằng `ADD CONSTRAINT … NOT VALID` rồi `VALIDATE CONSTRAINT` ở bước sau. Bước validate chỉ cần khóa nhẹ.
- Tách **deploy app** khỏi **chạy migration**. Chạy migration như một job riêng trước khi rollout (Module 13), không chạy trong lifespan của mỗi pod: 20 pod cùng chạy migration là công thức cho xung đột.

---

## 8. Outbox pattern: ghi DB và phát sự kiện

### 8.1. Vấn đề dual write

Sau khi tạo hóa đơn, `invoice-api` cần báo cho hệ thống khác: gửi email cho người mua, đồng bộ sang kế toán, gửi lên cơ quan thuế. Cách ngây thơ:

```python
await db.commit()
await broker.publish("invoice.created", payload)     # nếu tiến trình chết ở giữa hai dòng?
```

- Chết sau `commit`, trước `publish`: hóa đơn tồn tại nhưng **không ai được báo** (mất sự kiện).
- Đảo thứ tự (publish trước, commit sau) rồi commit thất bại: sự kiện về một hóa đơn **không tồn tại**.

Không có cách sắp xếp hai lệnh ghi vào hai hệ thống khác nhau sao cho nguyên tử, nếu không có giao thức phân tán như 2PC. Mà 2PC thì hầu hết broker hiện đại không hỗ trợ, và nó cũng có chi phí riêng.

### 8.2. Lời giải: ghi sự kiện vào cùng transaction

**Transactional outbox** (Chris Richardson, *microservices.io*) biến hai lệnh ghi thành một:

1. Trong **cùng transaction** tạo hóa đơn, `INSERT` một hàng vào bảng `outbox(id, payload, published_at)`. Hóa đơn và sự kiện cùng commit, hoặc cùng biến mất.
2. Một tiến trình **relay** đọc các hàng chưa phát, gửi lên broker, rồi đánh dấu `published_at`.

<!-- placeholder-outbox -->

<!-- fig:outbox -->
<figure markdown="span">
  ![Dual write so với transactional outbox](assets/figures/10/outbox.light.svg#only-light){ loading=lazy }
  ![Dual write so với transactional outbox](assets/figures/10/outbox.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 10.12 — Dual write so với transactional outbox.</figcaption>
</figure>
<!-- /fig -->

Relay có thể chết **sau khi gửi, trước khi đánh dấu**. Khi khởi động lại, nó gửi lại sự kiện đó. Vì vậy outbox cho **at-least-once**, không phải exactly-once, và phía tiêu thụ phải **idempotent**: lưu `event_id` đã xử lý, đúng kỹ thuật của mục 5.

### 8.3. Nhiều relay song song: `SKIP LOCKED`

Để tăng thông lượng, ta chạy nhiều relay cùng lúc. Mỗi relay lấy một lô 100 sự kiện bằng `SELECT … FOR UPDATE` để hai relay không gửi trùng (thí nghiệm `d7`, 4.000 sự kiện, mỗi lô gửi lên broker giả lập mất 5 ms):

| Khóa | 1 relay | 2 relay | 4 relay | Trùng |
|---|---|---|---|---|
| `FOR UPDATE` | 10.806/s | 11.044/s | 11.111/s | 0 |
| `FOR UPDATE SKIP LOCKED` | 9.930/s | 18.616/s | **36.963/s** | 0 |

<!-- placeholder-outbox-scale -->

<!-- fig:outbox-scale -->
<figure markdown="span">
  ![Số đo thật: relay outbox chỉ mở rộng theo số relay khi dùng SKIP LOCKED](assets/figures/10/outbox-scale.light.svg#only-light){ loading=lazy }
  ![Số đo thật: relay outbox chỉ mở rộng theo số relay khi dùng SKIP LOCKED](assets/figures/10/outbox-scale.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 10.13 — Số đo thật: relay outbox chỉ mở rộng theo số relay khi dùng SKIP LOCKED.</figcaption>
</figure>
<!-- /fig -->

Chỉ dùng `FOR UPDATE` thì thêm relay **vô ích**: relay 2 cố khóa cùng 100 hàng đầu tiên mà relay 1 đang giữ, nên phải chờ. Kết quả là các relay chạy tuần tự. `SKIP LOCKED` bảo Postgres **bỏ qua** những hàng đang bị khóa và lấy lô kế tiếp, nên thông lượng tăng gần tuyến tính theo số relay. Cả hai cách đều không trùng sự kiện, vì khóa hàng đảm bảo điều đó. Cái giá của `SKIP LOCKED` là thứ tự toàn cục không còn được giữ. Nếu người tiêu thụ cần thứ tự **theo hóa đơn**, hãy phân vùng theo `invoice_id` (mỗi relay một phân vùng) hoặc để broker giữ thứ tự theo khóa (partition key của Kafka).

Cùng kỹ thuật `FOR UPDATE SKIP LOCKED` này biến một bảng Postgres thành **hàng đợi công việc** đủ dùng cho hàng nghìn việc mỗi giây. Ở `ai-gateway`, đó là một lựa chọn thay Redis/Celery cho hàng đợi các lượt chạy LLM (Module 14).

---

## 9. Case Mekong Cloud: luồng ghi của `POST /v1/invoices`

Ghép tất cả lại thành một transaction duy nhất, giữ kết nối ~6,6 ms (số đo `d8`):

```mermaid
sequenceDiagram
    autonumber
    participant H as Handler
    participant D as get_session (yield, scope=function)
    participant P as PostgreSQL
    D->>P: BEGIN; set_config('app.tenant_id', t, true)
    H->>P: INSERT idempotency_keys … ON CONFLICT DO NOTHING RETURNING key
    alt khóa đã có chủ
        P-->>H: (rỗng) → SELECT response đã lưu → phát lại 201 / 422
    else giành được khóa
        H->>P: INSERT invoices + 12 invoice_lines (ORM flush)
        H->>P: UPDATE series_counter … RETURNING last_number (cấp số muộn nhất có thể)
        H->>P: INSERT outbox (invoice.created)
        H->>P: UPDATE idempotency_keys SET response_body
    end
    D->>P: COMMIT (trước khi gửi 201)
    Note over P: RLS chặn mọi hàng của tenant khác<br/>UNIQUE(tenant_id, series, number) là phòng tuyến cuối
```

| Quyết định | Lựa chọn | Lý do bằng số |
|---|---|---|
| Pool mỗi tiến trình | `pool_size=5, max_overflow=0`, `pool_timeout=2` | $a = 125 \times 0{,}0066 = 0{,}83$ erlang/pod; $P_{\text{chờ}} < 1\%$ |
| Tổng kết nối tới DB | ≤ 2 × core DB; PgBouncer khi autoscale | thông lượng đỉnh ở 2 × core (`d5`) |
| Cấp số | bộ đếm theo ký hiệu + khóa hàng, cấp cuối transaction | `MAX()+1`: 371/400 trùng; sequence: có khoảng trống |
| Idempotency | `ON CONFLICT DO NOTHING` trước, lưu response trong cùng transaction | 1 hóa đơn/khóa, 0 lỗi 500 (`d3`) |
| Tenant | `tenant_id` + RLS + `SET LOCAL` + role riêng | `SET` thường rò dữ liệu qua pool (`d4leak`) |
| Đọc danh sách | `selectinload`, `lazy="raise"` | 122 ms → 17,5 ms (`d1`) |
| Migration | expand/contract, `lock_timeout` | không timeout: API kẹt tới 1,7 s (`d6`) |
| Sự kiện | outbox + relay `SKIP LOCKED` | 37k sự kiện/s với 4 relay (`d7`) |

---

## Lỗi thường gặp & cách xử lý

| Triệu chứng | Nguyên nhân gốc | Cách xử lý |
|---|---|---|
| `MissingGreenlet: greenlet_spawn has not been called` | lazy load hoặc refresh thuộc tính hết hạn trong code async | `expire_on_commit=False`; nạp trước bằng `selectinload`; `lazy="raise"` để lộ lỗi sớm |
| `QueuePool limit … reached, connection timed out` | transaction giữ kết nối quá lâu (gọi API/LLM bên trong), rò session, hoặc pool quá nhỏ | đo thời gian giữ; rút I/O chậm ra khỏi transaction; tính pool bằng Little/Erlang C |
| p99 tăng khi **tăng** pool | DB quá tải CPU, hàng đợi chuyển vào DB | giảm tổng kết nối về ~2 × core DB; PgBouncer |
| Danh sách chậm dần theo `limit` | N+1 | `selectinload`; đếm truy vấn trong test |
| Số hóa đơn trùng | `MAX()+1` dưới READ COMMITTED | bộ đếm có khóa hàng + `UNIQUE` |
| Số hóa đơn nhảy cóc | dùng sequence, transaction rollback | bộ đếm transactional |
| Hóa đơn bị tạo hai lần khi POS retry | kiểm tra-rồi-ghi khóa idempotency | `INSERT … ON CONFLICT` trước, lưu response trong cùng transaction |
| Thỉnh thoảng thấy dữ liệu tenant khác | `SET` cấp session còn sót trên kết nối từ pool | `SET LOCAL` / `set_config(..., true)` |
| RLS "không có tác dụng" | app kết nối bằng chủ bảng hoặc superuser | role riêng; `FORCE ROW LEVEL SECURITY` |
| Deploy migration, toàn bộ API timeout vài giây | DDL chờ khóa sau transaction dài, chặn hàng đợi khóa | `lock_timeout`, retry migration; tách job báo cáo sang replica |
| `prepared statement "__asyncpg_stmt_…" does not exist` | asyncpg sau PgBouncer chế độ transaction | `max_prepared_statements` (PgBouncer ≥ 1.21) hoặc tắt cache prepared statement |
| Sự kiện mất khi tiến trình chết | publish ngoài transaction (dual write) | outbox |

## Tóm tắt (cheat-sheet)

- **Ba model**: `InvoiceIn` (Pydantic) → `Invoice` (ORM) → `InvoiceOut` (Pydantic, `from_attributes=True`). Không để Pydantic kích hoạt lazy load.
- **Session**: `async_sessionmaker(expire_on_commit=False)`; dependency `yield` + `session.begin()` + `scope="function"` → commit trước khi trả response, ngoại lệ → rollback.
- **Pool**: $L = \lambda S$ với $S$ là thời gian giữ kết nối; Erlang C cho xác suất chờ. Tổng kết nối tới DB ≈ 2 × core DB (+ spindle). `max_overflow=0`, `pool_timeout` ngắn.
- **N+1**: `selectinload` cho collection, `joinedload` cho nhiều-một; `lazy="raise"`; đếm truy vấn trong test.
- **Đọc-rồi-ghi là race** dưới READ COMMITTED. Dùng ràng buộc unique, `INSERT … ON CONFLICT`, `UPDATE … RETURNING`.
- **Cấp số liên tục**: bộ đếm theo ký hiệu + khóa hàng, cấp **cuối** transaction; $X_{\max} = 1/t_{\text{giữ khóa}}$.
- **Idempotency**: giành khóa trước, băm model đã validate, lưu response cùng transaction; khác payload → 422.
- **Multi-tenant**: `tenant_id` + RLS + `SET LOCAL` + role không sở hữu bảng.
- **Migration**: expand → dual write → backfill theo lô → chuyển đọc → contract; luôn `lock_timeout`.
- **Outbox**: sự kiện ghi cùng transaction; relay `FOR UPDATE SKIP LOCKED`; người tiêu thụ idempotent.

## Câu hỏi tự kiểm tra / phỏng vấn

**1.** Vì sao `InvoiceOut.model_validate(invoice)` có thể ném lỗi trong code async nhưng chạy được trong code đồng bộ?

<details markdown="1">
<summary>Đáp án</summary>

`from_attributes` đọc thuộc tính bằng `getattr`. Nếu `invoice.lines` chưa được nạp, ORM sẽ lazy load, tức phát truy vấn ngay trong `getattr`. Code đồng bộ làm được việc đó (âm thầm, và là nguồn của N+1). Trong async, I/O phải nằm sau một `await`, mà `getattr` không thể `await`, nên SQLAlchemy ném `MissingGreenlet`. Với `lazy="raise"` thì lỗi là `InvalidRequestError`, và Pydantic gói nó thành `get_attribute_error`. Cách sửa: nạp trước bằng `selectinload` trong repository.

</details>

**2.** Một dependency session dùng scope mặc định `"request"` và commit sau `yield`. Rủi ro là gì?

<details markdown="1">
<summary>Đáp án</summary>

Phần sau `yield` của scope `"request"` chạy **sau khi** response đã gửi. Client có thể nhận `201` trước khi `COMMIT` chạy. Nếu commit thất bại (deadlock, ràng buộc trì hoãn, mất kết nối) thì client tin rằng hóa đơn đã tồn tại trong khi không phải. Lỗi lúc này cũng không thể biến thành response lỗi được nữa. Dùng `scope="function"` để commit xong rồi mới gửi response.

</details>

**3.** `invoice-api` chạy 500 req/s, mỗi transaction giữ kết nối 6,6 ms. Cần bao nhiêu kết nối? Nếu một đồng nghiệp đưa lệnh gọi API thuế (200 ms) vào trong transaction thì sao?

<details markdown="1">
<summary>Đáp án</summary>

$a = 500 \times 0{,}0066 = 3{,}3$ erlang. Theo Erlang C, 8 kết nối cho $P_{\text{chờ}} \approx 2\%$ và 10 kết nối cho ≈ 0,2%, vậy 8–10 là đủ. Khi đưa lời gọi 200 ms vào transaction, $S \approx 0{,}207$ s nên $a \approx 103$ erlang, cần hơn 100 kết nối. Con số đó vượt xa mức tối ưu của DB (~2 × core), và database sẽ chậm cho mọi người. Đúng ra phải gọi API thuế **ngoài** transaction (hoặc đẩy qua outbox).

</details>

**4.** Trong thí nghiệm pool, tăng từ 8 lên 64 kết nối thì thông lượng giảm nhẹ nhưng latency request gần như không đổi. Giải thích.

<details markdown="1">
<summary>Đáp án</summary>

Với 64 client và mọi cấu hình pool, tổng số request trong hệ thống là như nhau (closed-loop). Theo Little, $W = N/X$, và thông lượng gần như không đổi nên latency gần như không đổi. Thứ thay đổi là **vị trí của hàng đợi**. Pool 8 thì request chờ trong pool phía app, còn truy vấn chạy nhanh (37 ms trong DB). Pool 64 thì request không chờ pool, nhưng 64 truy vấn tranh 4 core, mỗi truy vấn mất 284 ms. Thông lượng giảm nhẹ vì chi phí chuyển ngữ cảnh và tranh chấp. Ngoài ra, truy vấn chạy lâu hơn thì giữ khóa lâu hơn, và đó là chi phí ẩn.

</details>

**5.** Vì sao `SELECT max(number)+1` cho ra số trùng? Đổi sang `SERIALIZABLE` có sửa được không?

<details markdown="1">
<summary>Đáp án</summary>

Dưới READ COMMITTED, mỗi câu lệnh thấy snapshot tại thời điểm nó bắt đầu. 32 transaction cùng đọc `max` khi chưa ai commit, nên cùng tính ra một giá trị. `SERIALIZABLE` (SSI của Postgres) sẽ phát hiện xung đột đọc-ghi và **hủy** các transaction vi phạm với lỗi serialization failure. Dữ liệu khi đó đúng, nhưng app phải retry, và dưới tải cao tỉ lệ retry rất lớn. Bộ đếm có khóa hàng xếp hàng các transaction một cách tự nhiên, không phát sinh retry.

</details>

**6.** Sequence của Postgres không trùng số. Tại sao không dùng nó cho số hóa đơn?

<details markdown="1">
<summary>Đáp án</summary>

`nextval()` không transactional: số đã cấp không được trả lại khi rollback. Thí nghiệm có 5% rollback và tạo ra 19 khoảng trống. Pháp luật yêu cầu số hóa đơn liên tục, nên khoảng trống là vi phạm. Sequence phù hợp cho khóa chính, nơi khoảng trống vô hại.

</details>

**7.** Thiết kế idempotency "SELECT rồi INSERT, có PRIMARY KEY" cho đúng một hóa đơn. Vì sao vẫn không chấp nhận được?

<details markdown="1">
<summary>Đáp án</summary>

Các request trùng đến đồng thời đều đi qua `SELECT`, đều xử lý, rồi bị ràng buộc unique chặn ở `INSERT` cuối. Transaction của chúng rollback và client nhận **500** (39/50 trong thí nghiệm) cho một request hợp lệ. Client sẽ retry, log ngập lỗi giả, và tài nguyên bị lãng phí cho việc xử lý rồi vứt bỏ. Giành khóa **trước** bằng `ON CONFLICT DO NOTHING` khiến bản sao chờ bản gốc commit rồi phát lại response đã lưu.

</details>

**8.** Vì sao nên băm `body.model_dump_json()` thay vì bytes thô của request khi kiểm tra "cùng khóa, khác payload"?

<details markdown="1">
<summary>Đáp án</summary>

Hai request có cùng ngữ nghĩa có thể khác nhau ở bytes: thứ tự khóa JSON, khoảng trắng, `1` so với `1.0`, chuỗi số so với số (sau coercion). Model đã validate là **dạng chuẩn hóa**. `model_dump_json()` xuất các trường theo thứ tự khai báo và giá trị đã ép kiểu, nên hash phản ánh ngữ nghĩa thay vì cách client định dạng JSON. Thí nghiệm: đổi thứ tự khóa vẫn được phát lại, đổi số tiền thì nhận 422.

</details>

**9.** RLS đã bật, nhưng test cho thấy một tenant vẫn đọc được hóa đơn của tenant khác. Liệt kê các nguyên nhân có thể.

<details markdown="1">
<summary>Đáp án</summary>

(1) App kết nối bằng **chủ bảng** mà chưa bật `FORCE ROW LEVEL SECURITY`, hoặc bằng superuser / role có `BYPASSRLS`. (2) Tenant được đặt bằng `SET` cấp session, rồi một request khác dùng lại kết nối từ pool mà không đặt lại (`d4leak`). (3) Policy chỉ có `USING` cho `SELECT`, còn đường ghi lại không có `WITH CHECK`, nên dữ liệu bị ghi sai tenant từ trước. (4) Truy vấn đi qua một view hoặc hàm `SECURITY DEFINER` chạy với quyền của chủ sở hữu.

</details>

**10.** Thêm một cột nullable chỉ tốn vài mili giây. Vì sao migration đó vẫn làm API timeout?

<details markdown="1">
<summary>Đáp án</summary>

`ALTER TABLE` cần khóa `ACCESS EXCLUSIVE`. Nếu có transaction dài đang giữ `ACCESS SHARE` (báo cáo, transaction bị bỏ quên ở trạng thái idle in transaction), DDL phải chờ. Khóa trong Postgres cấp theo hàng đợi, nên mọi `SELECT` đến sau phải đứng sau DDL đang chờ, và API bị chặn suốt thời gian đó (tới 1,7 s trong `d6`). Đặt `lock_timeout` để DDL tự hủy và thử lại, đồng thời đặt `idle_in_transaction_session_timeout` để dọn các transaction bị bỏ quên.

</details>

**11.** Outbox cho at-least-once. Kể hai tình huống sinh trùng sự kiện và cách người tiêu thụ xử lý.

<details markdown="1">
<summary>Đáp án</summary>

(1) Relay gửi lên broker thành công rồi chết trước khi `UPDATE published_at` commit. Khi khởi động lại, nó gửi lại sự kiện đó. (2) Broker nhận sự kiện nhưng ack bị mất, nên relay timeout và gửi lại. Người tiêu thụ lưu `event_id` đã xử lý trong cùng transaction với hiệu ứng của mình (một bảng có khóa chính `event_id`, dùng `INSERT … ON CONFLICT DO NOTHING`), y như idempotency key phía API.

</details>

**12.** Khi nào bạn chọn DB riêng mỗi tenant thay vì bảng chung + RLS?

<details markdown="1">
<summary>Đáp án</summary>

Khi số tenant ít và mỗi tenant lớn, khi có yêu cầu pháp lý hoặc hợp đồng về cô lập vật lý hay vị trí dữ liệu, khi cần sao lưu và khôi phục **riêng từng tenant**, hoặc khi một tenant gây tải quá lớn ("noisy neighbor") cần tách hẳn. Cái giá là migration và vận hành nhân theo số tenant. Với 3.000 tenant nhỏ của `invoice-api`, bảng chung + RLS hợp lý hơn. Có thể kết hợp: tenant cực lớn được chuyển sang DB riêng (mô hình lai).

</details>

## Bài tập thực hành

1. **Đếm truy vấn trong test.** Viết fixture pytest gắn listener `before_cursor_execute` và assert `GET /v1/invoices?limit=50` phát ≤ 3 truy vấn. Cố ý bỏ `selectinload` để thấy test đỏ.
2. **Chạy lại thí nghiệm pool trên máy bạn.** Khởi động Postgres (Docker: `docker run -e POSTGRES_HOST_AUTH_METHOD=trust -p 5432:5432 postgres:16`), đặt `PG_DSN`, chạy `python scripts/bench/bench_db.py --only d5`. Điểm đỉnh có rơi vào 2 × số core của máy bạn không?
3. **Idempotency kiểu 409.** Cài biến thể ở mục 5.4: giành khóa trong transaction riêng với `status='processing'`, bản sao nhận `409` + `Retry-After`. Viết test 50 request đồng thời và so số kết nối bị giữ với thiết kế trong bài.
4. **RLS cho đường ghi.** Thêm `WITH CHECK (tenant_id = current_setting('app.tenant_id')::int)` vào policy. Viết test chứng minh tenant 1 không thể `INSERT` hóa đơn mang `tenant_id = 2`.

## Tài liệu tham khảo

- Junwen Yang, Cong Yan, Pranav Subramaniam, Shan Lu, Alvin Cheung. *How not to structure your database-backed web applications: a study of performance bugs in the wild*. **ICSE 2018**. [PDF (NSF PAR)](https://par.nsf.gov/servlets/purl/10067547)
- Tse-Hsun Chen, Weiyi Shang, Zhen Ming Jiang, Ahmed E. Hassan, Mohamed Nasser, Parminder Flora. *Detecting performance anti-patterns for applications developed using object-relational mapping*. **ICSE 2014**.
- John D. C. Little. *A Proof for the Queuing Formula: L = λW*. Operations Research 9(3), 1961.
- Brett Wooldridge. *About Pool Sizing* — HikariCP wiki. [github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing)
- PostgreSQL 16 Documentation: [Row Security Policies](https://www.postgresql.org/docs/16/ddl-rowsecurity.html), [Explicit Locking](https://www.postgresql.org/docs/16/explicit-locking.html), [INSERT … ON CONFLICT](https://www.postgresql.org/docs/16/sql-insert.html), [Sequence functions](https://www.postgresql.org/docs/16/functions-sequence.html), [Transaction isolation](https://www.postgresql.org/docs/16/transaction-iso.html).
- SQLAlchemy 2.1 Documentation: [Asynchronous I/O (asyncio)](https://docs.sqlalchemy.org/en/21/orm/extensions/asyncio.html), [Relationship loading techniques](https://docs.sqlalchemy.org/en/21/orm/queryguide/relationships.html), [Connection pooling](https://docs.sqlalchemy.org/en/21/core/pooling.html).
- Alembic Documentation. [alembic.sqlalchemy.org](https://alembic.sqlalchemy.org/)
- Danilo Sato. *Parallel Change*. martinfowler.com, 2014. [martinfowler.com/bliki/ParallelChange.html](https://martinfowler.com/bliki/ParallelChange.html)
- Chris Richardson. *Pattern: Transactional outbox*. [microservices.io/patterns/data/transactional-outbox.html](https://microservices.io/patterns/data/transactional-outbox.html)
- J. Jena, S. Dalal. *The Idempotency-Key HTTP Header Field*. IETF httpapi WG, draft-ietf-httpapi-idempotency-key-header-07, 10/2025 (Internet-Draft, đã hết hạn). [datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/)
- Brandur Leach. *Implementing Stripe-like Idempotency Keys in Postgres*, 2017. [brandur.org/idempotency-keys](https://brandur.org/idempotency-keys)
- Stripe API Reference: [Idempotent requests](https://docs.stripe.com/api/idempotent_requests).
- Nghị định 123/2020/NĐ-CP quy định về hóa đơn, chứng từ (Điều 10 — nội dung hóa đơn, số hóa đơn).
- PgBouncer: [Configuration — max_prepared_statements](https://www.pgbouncer.org/config.html).
