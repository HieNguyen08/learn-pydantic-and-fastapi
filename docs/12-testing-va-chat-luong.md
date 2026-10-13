# Module 12 — Testing & chất lượng

> Thời lượng: ~45 phút · Mức độ: Trung bình → Nâng cao · Tiên quyết: Module 08, 10, 11

Mười một module trước đã đưa vào `invoice-api` hàng chục quy tắc: chữ số kiểm tra MST, làm tròn thuế half-up, idempotency, RLS, 404 cho tenant khác, `extra="forbid"`… Mỗi quy tắc là một chỗ có thể bị phá vỡ ở lần sửa code tiếp theo. Module này trả lời: **viết test gì, ở tầng nào, bằng kỹ thuật nào** để bắt được lỗi trước khi lỗi tới tay 3.000 doanh nghiệp. Trọng tâm là ba kỹ thuật mà test viết tay theo ví dụ không làm được: **property-based testing**, **fuzz theo schema** và **mutation testing**.

Mọi số đo và mọi "lỗi được tìm thấy" trong bài đều đến từ `scripts/bench/bench_testing.py`, chạy trên Hypothesis 6.169, Schemathesis 4.31, FastAPI 0.143 và PostgreSQL 16. Các lỗi được **cài sẵn** vào code mẫu `testing_subject.py`. Đó là những lỗi mình đã thấy ngoài thực tế.

## Mục tiêu học tập

Sau module này, bạn có thể:

1. Chọn **tầng test** (unit, tích hợp trong tiến trình, tích hợp với DB, end-to-end) cho từng loại rủi ro, dựa trên chi phí đo được của mỗi tầng.
2. Viết test API với `TestClient` hoặc `httpx.AsyncClient` + `ASGITransport`, xử lý đúng **lifespan**, thay thế phụ thuộc bằng `dependency_overrides`.
3. Cô lập dữ liệu giữa các test bằng **transaction + savepoint rollback**, nhanh hơn TRUNCATE ~5 lần.
4. Viết **property-based test** với Hypothesis: thuộc tính round-trip, oracle, bất biến; hiểu **shrinking**.
5. Chạy **fuzz theo schema** bằng Schemathesis và đọc kết quả, kể cả những lỗi "không phải bug nhưng vẫn là bug" như lệch giữa OpenAPI và hành vi thật.
6. Đo chất lượng bộ test bằng **mutation testing**, và phát hiện **breaking change** trong OpenAPI trước khi merge.

---

## 1. Test cái gì, ở tầng nào

### 1.1. Kim tự tháp, cúp, và chi phí thật

Kim tự tháp test (Mike Cohn, 2009) khuyên viết nhiều unit test và ít test end-to-end. Lý do: test ở tầng thấp nhanh, ổn định và chỉ rõ chỗ hỏng. "Cúp test" (testing trophy, Kent C. Dodds) đặt trọng tâm vào **test tích hợp**, vì phần lớn lỗi của ứng dụng web nằm ở **chỗ ghép**: route ↔ dependency ↔ model ↔ database.

Với một API FastAPI, mình thấy cách chia sau hợp lý nhất:

| Tầng | Kiểm cái gì | Công cụ | Chi phí mỗi test (đo được) |
|---|---|---|---|
| Unit (thuần) | quy tắc nghiệp vụ: MST, làm tròn thuế, tổng hóa đơn; validator của model | pytest + **Hypothesis** | µs |
| Tích hợp trong tiến trình | route, validation, status code, response model, DI, exception handler | `AsyncClient` + `ASGITransport`, `dependency_overrides` | ~0,3–0,5 ms/request |
| Tích hợp với DB | truy vấn, ràng buộc, RLS, idempotency, transaction | PostgreSQL thật (container), savepoint rollback | ~4 ms/test |
| Hợp đồng / fuzz | mọi endpoint so với OpenAPI | **Schemathesis** | giây (cho cả API) |
| End-to-end | cấu hình, mạng, proxy, migration | vài smoke test trên môi trường staging | giây–phút |

<!-- placeholder-pyramid -->

<!-- fig:pyramid -->
<figure markdown="span">
  ![Các tầng test cho một API FastAPI, chi phí đo được và ví dụ quy tắc ở từng tầng](assets/figures/12/pyramid.light.svg#only-light){ loading=lazy }
  ![Các tầng test cho một API FastAPI, chi phí đo được và ví dụ quy tắc ở từng tầng](assets/figures/12/pyramid.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 12.1 — Các tầng test cho một API FastAPI, chi phí đo được và ví dụ quy tắc ở từng tầng.</figcaption>
</figure>
<!-- /fig -->

Nguyên tắc chọn tầng: **kiểm mỗi quy tắc ở tầng thấp nhất mà quy tắc đó còn có nghĩa**. Chữ số kiểm tra MST là hàm thuần, nên test unit với hàng nghìn input. "Tenant 7 nhận 404 khi đọc hóa đơn của tenant 9" cần route + DI + DB, nên đó là test tích hợp với DB. Còn "proxy chặn body 4 MiB" chỉ có nghĩa ở end-to-end.

### 1.2. Ba cách gọi app trong test: số đo

Thí nghiệm `t1` gọi cùng một app (một `GET /health` và một `POST` hóa đơn 12 dòng) bằng ba cách:

| Cách gọi | `GET /health` | `POST /v1/invoices` |
|---|---|---|
| `TestClient` (đồng bộ) | 800 µs | 1.108 µs |
| `httpx.AsyncClient` + `ASGITransport` | **309 µs** | **544 µs** |
| uvicorn thật + `httpx.Client` qua TCP | 1.027 µs | 1.233 µs |

<!-- placeholder-clients -->

<!-- fig:clients -->
<figure markdown="span">
  ![Số đo thật: chi phí mỗi request khi gọi app bằng TestClient, AsyncClient + ASGITransport và uvicorn thật](assets/figures/12/clients.light.svg#only-light){ loading=lazy }
  ![Số đo thật: chi phí mỗi request khi gọi app bằng TestClient, AsyncClient + ASGITransport và uvicorn thật](assets/figures/12/clients.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 12.2 — Số đo thật: chi phí mỗi request khi gọi app bằng TestClient, AsyncClient + ASGITransport và uvicorn thật.</figcaption>
</figure>
<!-- /fig -->

`TestClient` chạy app trong một **event loop riêng ở luồng khác** (qua `anyio` portal), nên mỗi request tốn thêm một lần chuyển luồng. Nó tiện cho test đồng bộ, nhưng chậm hơn ~2,5 lần và **không thể dùng chung** event loop với các fixture async khác (ví dụ session SQLAlchemy async). Với một codebase toàn `async def` như `invoice-api`, dùng `AsyncClient`:

```python
import httpx
import pytest

from app.main import app


@pytest.fixture
async def client():
    async with app.router.lifespan_context(app):              # ASGITransport KHÔNG tự chạy lifespan
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
```

Cái bẫy đã kiểm chứng: `ASGITransport` **không gửi sự kiện lifespan**. Một app khởi tạo pool trong lifespan sẽ thấy `app.state.pool` là `None` khi test (chạy thật: `{'pool': None}`). `TestClient` dùng trong `with` thì chạy lifespan. Với `AsyncClient`, bọc bằng `app.router.lifespan_context(app)` như trên.

### 1.3. Thay phụ thuộc: `dependency_overrides`

Module 08 đã giới thiệu cơ chế này. Trong test, ta thay **đúng phần cần thay** và giữ phần còn lại chạy thật:

```python
from app.deps import current_principal, get_session
from app.security import Principal


def as_tenant(tenant_id: int, *scopes: str):
    async def fake() -> Principal:
        return Principal(sub="test", tid=tenant_id, scope=" ".join(scopes))
    return fake


async def test_tenant_khac_nhan_404(client, db_session, invoice_of_tenant_9):
    app.dependency_overrides[get_session] = lambda: db_session                  # session của test (mục 2)
    app.dependency_overrides[current_principal] = as_tenant(7, "invoice:read")
    r = await client.get(f"/v1/invoices/{invoice_of_tenant_9.id}")
    assert r.status_code == 404
    app.dependency_overrides.clear()
```

Một lưu ý về `Security(current_principal, scopes=[...])`: khi override `current_principal`, hàm giả **không nhận `SecurityScopes`**, nên phần kiểm scope cũng bị thay. Test BFLA (thiếu scope → 403) vì vậy phải dùng **token thật** ký bằng khóa test, không dùng override. Quy tắc chung: override những gì **ở ngoài** đối tượng cần test, đừng override chính thứ đang được test.

---

## 2. Test với database thật

### 2.1. Vì sao không mock database

Mock repository thì test nhanh, nhưng mọi thứ Module 10 dạy đều **nằm trong database**: ràng buộc unique chặn hóa đơn trùng số, `ON CONFLICT` cho idempotency, RLS chặn tenant khác, `lazy="raise"`. Một repository giả không có những hành vi đó, nên test xanh trong khi production đỏ. Lời khuyên thực tế: **chạy PostgreSQL thật trong container** (testcontainers, hoặc service container của CI), cùng phiên bản với production. SQLite "để test cho nhanh" có ngữ nghĩa khác: không có RLS, kiểu dữ liệu lỏng hơn, `ON CONFLICT` khác cú pháp.

### 2.2. Cô lập giữa các test: ba chiến lược, số đo

Mỗi test phải bắt đầu với database sạch. Thí nghiệm `t2` so ba cách trên một schema 12 bảng, mỗi test tạo một hóa đơn 12 dòng rồi đọc lại:

| Chiến lược | ms/test | Ghi chú |
|---|---|---|
| tạo lại bảng (`drop_all` + `create_all`) | 61,5 | DDL đắt, khóa catalog |
| `TRUNCATE` mọi bảng sau test | 22,0 | phải liệt kê bảng, `RESTART IDENTITY CASCADE` |
| **transaction + savepoint, rollback** | **4,4** | test không bao giờ thật sự commit |

<!-- placeholder-db-isolation -->

<!-- fig:db-isolation -->
<figure markdown="span">
  ![Số đo thật: ba chiến lược cô lập database giữa các test, và cơ chế transaction + savepoint](assets/figures/12/db-isolation.light.svg#only-light){ loading=lazy }
  ![Số đo thật: ba chiến lược cô lập database giữa các test, và cơ chế transaction + savepoint](assets/figures/12/db-isolation.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 12.3 — Số đo thật: ba chiến lược cô lập database giữa các test, và cơ chế transaction + savepoint.</figcaption>
</figure>
<!-- /fig -->

Với 800 test có chạm DB, khác biệt là **50 giây so với 4 giây**. Cách làm với SQLAlchemy 2.x:

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def db_session(engine):
    async with engine.connect() as conn:
        trans = await conn.begin()                          # transaction ngoài cùng của test
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint",
                               expire_on_commit=False)
        try:
            yield session                                   # code app gọi commit() → chỉ RELEASE SAVEPOINT
        finally:
            await session.close()
            await trans.rollback()                          # dọn sạch mọi thứ test đã ghi
```

`join_transaction_mode="create_savepoint"` khiến mọi `session.begin()` / `commit()` của code ứng dụng trở thành **savepoint** bên trong transaction của test. App vẫn "commit" và vẫn đọc lại được dữ liệu của chính nó, nhưng cuối test mọi thứ biến mất.

Giới hạn cần biết: cách này **không** test được hành vi cần **nhiều kết nối** thấy dữ liệu của nhau, vì dữ liệu chưa bao giờ thật sự commit. Ví dụ là cuộc đua idempotency (Module 10, `d3`) hay khóa hàng khi cấp số. Những test đồng thời đó phải commit thật và dọn bằng `TRUNCATE`. Hãy đánh dấu chúng (`@pytest.mark.concurrency`) và chạy riêng.

---

## 3. Property-based testing

### 3.1. Từ ví dụ đến thuộc tính

Một test ví dụ khẳng định: "với **input này**, kết quả là **cái này**". Một **property-based test** khẳng định: "với **mọi** input thỏa điều kiện X, **thuộc tính** P đúng". Thư viện sinh hàng trăm input, cố tìm phản ví dụ, rồi **thu nhỏ** (shrink) phản ví dụ đó về dạng đơn giản nhất. Ý tưởng bắt đầu từ **QuickCheck** (Claessen & Hughes, ICFP 2000) cho Haskell. **Hypothesis** (MacIver và cộng sự, JOSS 2019) mang nó sang Python, với một cải tiến quan trọng: shrink trên **chuỗi lựa chọn ngẫu nhiên** sinh ra input, thay vì trên chính input. Nhờ đó shrinking hoạt động với mọi strategy, kể cả strategy tự định nghĩa.

<!-- placeholder-pbt -->

<!-- fig:pbt -->
<figure markdown="span">
  ![Vòng lặp property-based testing: sinh input, kiểm thuộc tính, tìm phản ví dụ và thu nhỏ](assets/figures/12/pbt.light.svg#only-light){ loading=lazy }
  ![Vòng lặp property-based testing: sinh input, kiểm thuộc tính, tìm phản ví dụ và thu nhỏ](assets/figures/12/pbt.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 12.4 — Vòng lặp property-based testing: sinh input, kiểm thuộc tính, tìm phản ví dụ và thu nhỏ.</figcaption>
</figure>
<!-- /fig -->

Khó nhất là **tìm thuộc tính**. Năm mẫu thuộc tính dùng được ngay cho API:

| Mẫu | Ví dụ ở `invoice-api` |
|---|---|
| **Round-trip** (mã hóa rồi giải mã ra lại chính nó) | `M.model_validate_json(m.model_dump_json()) == m` cho mọi model trả ra |
| **Oracle** (so với bản cài đặt khác, chậm nhưng hiển nhiên đúng) | thuế tính bằng `Fraction` so với thuế tính bằng `Decimal` |
| **Bất biến** | `total == before + tax`; `0 ≤ tax − exact ≤ 0,5` |
| **Phát hiện lỗi** (thay đổi nhỏ phải bị phát hiện) | đổi một chữ số của MST hợp lệ → không còn hợp lệ |
| **Idempotence / không phụ thuộc thứ tự** | gửi lại cùng request với cùng `Idempotency-Key` → cùng response |

### 3.2. Thí nghiệm: ba lỗi thật, test ví dụ bỏ sót cả ba

Thí nghiệm `t3` cài ba lỗi. Mỗi lỗi có một bộ test ví dụ "hợp lý" mà người viết code thường tự viết:

| Lỗi cài sẵn | Test ví dụ | Hypothesis | Phản ví dụ sau shrink |
|---|---|---|---|
| MST: so `check[-1]` với chữ số cuối, nên khi `check = 10` thì chấp nhận chữ số `0` | **qua** (bỏ sót) | tìm thấy sau **24** input | `'1050360970'` |
| Thuế: `round(amount * rate / 100)`, tức làm tròn kiểu **ngân hàng** (half-even) qua float | **qua** (bỏ sót) | tìm thấy sau **70** input | `(525, 10)` → 52,5 bị làm tròn thành **52** thay vì 53 |
| Round-trip: `field_serializer` tự định dạng `datetime` bằng `strftime` | **qua** (bỏ sót) | tìm thấy sau **3** input | `datetime(999, 1, 1)` → `"999-01-01T…"` không còn là ISO 8601 hợp lệ |

<!-- placeholder-pbt-results -->

<!-- fig:pbt-results -->
<figure markdown="span">
  ![Số đo thật: ba lỗi cài sẵn đều lọt qua test ví dụ và đều bị Hypothesis tìm ra](assets/figures/12/pbt-results.light.svg#only-light){ loading=lazy }
  ![Số đo thật: ba lỗi cài sẵn đều lọt qua test ví dụ và đều bị Hypothesis tìm ra](assets/figures/12/pbt-results.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 12.5 — Số đo thật: ba lỗi cài sẵn đều lọt qua test ví dụ và đều bị Hypothesis tìm ra.</figcaption>
</figure>
<!-- /fig -->

Cả ba lỗi đều thuộc loại "vùng biên mà người viết test không nghĩ tới":

- **MST**: 1/11 tiền tố cho ra `check = 10`. Test ví dụ dùng vài MST thật, và MST thật thì không bao giờ rơi vào trường hợp đó.
- **Thuế**: chỉ sai khi tích `amount × rate` chia 100 dư **đúng 50**. Các số tròn như 100.000 hay 27.500 không chạm tới.
- **Round-trip**: serializer tự viết còn làm mất micro giây và múi giờ. Hypothesis báo phản ví dụ "đơn giản nhất" sau shrink: năm có 3 chữ số. Đó là một trường hợp **chưa ai nghĩ tới** khi viết serializer.

Code thuộc tính cho lỗi thuế, đủ ngắn để viết cho mọi hàm tiền tệ:

```python
from fractions import Fraction

from hypothesis import given, strategies as st


@given(st.integers(min_value=0, max_value=10**12), st.sampled_from([0, 5, 8, 10]))
def test_thue_lam_tron_nua_len(amount, rate):
    exact = Fraction(amount * rate, 100)                    # oracle: số hữu tỉ chính xác
    got = line_tax(amount, rate)
    assert -Fraction(1, 2) < got - exact <= Fraction(1, 2)  # gần nhất; đúng 0,5 thì làm tròn LÊN
```

### 3.3. Strategy từ model Pydantic

Hypothesis sinh được dữ liệu cho model Pydantic bằng `st.from_type(Model)` hoặc `st.builds(Model, ...)`. Nhưng với các ràng buộc phức tạp (MST hợp lệ, tổng phải khớp các dòng), strategy tự viết hiệu quả hơn hẳn so với sinh ngẫu nhiên rồi lọc:

```python
from hypothesis import strategies as st

WEIGHTS = (31, 29, 23, 19, 17, 13, 7, 5, 3)


@st.composite
def mst_hop_le(draw) -> str:
    first9 = draw(st.text(alphabet="0123456789", min_size=9, max_size=9)
                  .filter(lambda s: s[2:9] != "0000000"))
    check = 10 - sum(w * int(c) for w, c in zip(WEIGHTS, first9)) % 11
    if check == 10:                                       # tiền tố không hợp lệ: cho Hypothesis sinh lại
        from hypothesis import reject
        reject()
    return first9 + str(check)


line = st.fixed_dictionaries({
    "name": st.text(min_size=1, max_size=200),
    "quantity": st.integers(1, 10_000),
    "unit_price": st.integers(0, 10**9),
    "vat_rate": st.sampled_from(["0", "5", "8", "10", "KCT", "KKKNT"]),
})
invoice = st.fixed_dictionaries({"seller_tax_code": mst_hop_le(), "lines": st.lists(line, min_size=1, max_size=50)})
```

Thuộc tính tích hợp mạnh nhất cho `invoice-api`: **với mọi hóa đơn hợp lệ được sinh ra, `POST` trả 201, và `GET` lại trả đúng dữ liệu đó** (round-trip qua HTTP + DB). Một test đó phủ validation, serialization, mapping ORM và cấu hình DB.

### 3.4. Vận hành trong CI

- Mặc định Hypothesis chạy 100 ví dụ mỗi test. Đặt **profile**: `dev` 50 ví dụ cho vòng lặp nhanh, `ci` 500 ví dụ, `nightly` 10.000 ví dụ.
- Phản ví dụ được lưu vào **database ví dụ** (`.hypothesis/`) và được thử lại đầu tiên ở lần chạy sau. Trong CI, cache thư mục này giữa các lần chạy.
- Khi Hypothesis tìm ra lỗi, thêm phản ví dụ vào `@example(...)` để nó thành test hồi quy cố định.

---

## 4. Fuzz theo schema: Schemathesis

### 4.1. Ý tưởng

FastAPI sinh ra một **OpenAPI** mô tả chính xác mọi endpoint, tham số, body và response. Đặc tả này đủ để **tự động sinh test**:

- sinh request **hợp lệ** theo schema → kiểm server không trả 5xx và response khớp schema;
- sinh request **không hợp lệ** → kiểm server từ chối bằng 4xx.

**Schemathesis** (Hatfield-Dodds & Dygalo, ICSE 2022 poster, arXiv:2112.10328) làm đúng việc đó, xây trên Hypothesis. Trong đánh giá của bài báo, trên 16 dịch vụ mã nguồn mở, nó tìm được **từ 1,4 đến 4,5 lần** nhiều lỗi khác nhau hơn công cụ đứng thứ hai. Hướng nghiên cứu này còn có **RESTler** (Atlidakis, Godefroid, Polishchuk, ICSE 2019; fuzz có trạng thái, suy ra phụ thuộc giữa các request) và **EvoMaster** (Arcuri, TOSEM 2019; tìm kiếm tiến hóa, có cả chế độ white-box). Khảo sát của Golmohammadi, Zhang và Arcuri (*Testing RESTful APIs: A Survey*, TOSEM 2023) tổng hợp toàn bộ lĩnh vực.

<!-- placeholder-fuzz -->

<!-- fig:fuzz -->
<figure markdown="span">
  ![Fuzz theo schema với Schemathesis và những lỗi nó tìm ra trên app mẫu](assets/figures/12/fuzz.light.svg#only-light){ loading=lazy }
  ![Fuzz theo schema với Schemathesis và những lỗi nó tìm ra trên app mẫu](assets/figures/12/fuzz.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 12.6 — Fuzz theo schema với Schemathesis và những lỗi nó tìm ra trên app mẫu.</figcaption>
</figure>
<!-- /fig -->

### 4.2. Thí nghiệm: một app có ba lỗi cài sẵn

App mẫu có hai endpoint và ba lỗi:

```python
@app.post("/v1/invoices", status_code=201, response_model=InvoiceOut)
async def create(inv: InvoiceIn):
    total = sum(l.quantity * l.unit_price for l in inv.lines)
    code = inv.buyer_name.encode("ascii", errors="strict")          # LỖI 1: tên có dấu → 500
    return {"id": 1, "total": total, "average_line": total // len(inv.lines)}

@app.get("/v1/invoices", response_model=list[InvoiceOut])
async def search(limit: Annotated[int, Query(ge=0, le=200)] = 50):
    per_page = 1000 // limit                                          # LỖI 2: limit=0 → ZeroDivisionError
    return [{"id": i, "total": 1000, "average_line": None} for i in range(min(limit, 3))]   # LỖI 3: sai schema
```

Lệnh chạy:

```bash
schemathesis run http://127.0.0.1:8000/openapi.json --checks all --max-examples 200 --continue-on-failure
```

Kết quả trong **11,6 giây**, với 485 test case:

| Endpoint | Schemathesis báo | Nguyên nhân |
|---|---|---|
| `GET /v1/invoices` | **Server error** (`?limit=199`) | lỗi 3: `average_line: None` vi phạm `response_model` → FastAPI trả 500 |
| `POST /v1/invoices` | **Server error** với `buyer_name` chứa ký tự ngoài ASCII | lỗi 1 |
| `POST /v1/invoices` | **API accepted schema-violating request**: `"unit_price": false` → 201 | Pydantic chế độ **lax** ép `false` → `0`, trong khi OpenAPI ghi `type: integer` |
| `POST /v1/invoices` | **Undocumented HTTP status code** 400 với body không phải JSON | FastAPI trả 400 "There was an error parsing the body", nhưng OpenAPI chỉ khai báo 201, 422 |
| `OPTIONS /v1/invoices` | **Invalid Allow header** | response 405 không liệt kê đủ phương thức |

Sau khi sửa lỗi 3 và chạy lại, Schemathesis báo **Server error với `?limit=0`**, tức lỗi 2. Lần đầu nó chưa hiện vì Schemathesis **gom các lỗi cùng chữ ký** (cùng endpoint, cùng loại kiểm tra). Kết luận thực hành: sửa xong thì chạy lại, cho tới khi sạch.

Hai phát hiện "ngoài kế hoạch" đáng giá hơn cả ba lỗi cài sẵn:

1. **Lệch giữa Pydantic lax và JSON Schema**. OpenAPI hứa `integer`, nhưng server nhận `false`. Client sinh từ OpenAPI không bao giờ gửi `false`, nhưng một client viết tay thì có thể, và khi đó sai sót bị nuốt mất. Cách sửa: `ConfigDict(strict=True)` cho model request, hoặc `StrictInt` cho trường tiền (Module 01, 03).
2. **Mã trạng thái chưa khai báo**. 400, 413, 429, 401 đều thật sự xảy ra (Module 11), nhưng OpenAPI không nói. Khai báo chúng bằng `responses={...}` để client biết phải xử lý.

### 4.3. Đưa vào CI

Chạy Schemathesis trên app trong tiến trình với `schemathesis.openapi.from_asgi(...)` trong pytest, hoặc dùng CLI với một server tạm. Có hai chế độ đáng dùng:

- **Mỗi PR**: `--max-examples 50`, `--checks all`, chỉ các endpoint bị đổi. Mất vài giây đến vài chục giây.
- **Hằng đêm**: `--max-examples 1000`, thêm pha **stateful** (Schemathesis dùng `links` trong OpenAPI để nối `POST` → `GET /{id}`), chạy trên dữ liệu thật hơn.

---

## 5. Mutation testing: test của bạn có thật sự kiểm tra gì không?

### 5.1. Ý tưởng

**Độ phủ dòng** (line coverage) chỉ nói một dòng **đã chạy**, không nói kết quả của nó **đã được kiểm**. Mutation testing (DeMillo, Lipton & Sayward, 1978) đo trực tiếp: tạo nhiều **đột biến** của code, mỗi đột biến là một thay đổi nhỏ như `+` → `-`, `<` → `<=`, `and` → `or`, `10` → `11`, rồi chạy bộ test trên từng đột biến. Đột biến bị test bắt là **bị diệt**, đột biến làm test vẫn xanh là **sống sót**:

$$
\text{điểm đột biến} = \frac{\text{số đột biến bị diệt}}{\text{tổng số đột biến} - \text{số đột biến tương đương}}
$$

**Đột biến tương đương** là đột biến không đổi hành vi, ví dụ `check < 10` → `check < 11` khi `check` không bao giờ vượt 10. Không test nào diệt được chúng, nên phải loại ra.

Ở quy mô lớn, Google chạy mutation testing trong code review. Họ chỉ báo đột biến ở **dòng vừa sửa** và lọc đột biến "không đáng quan tâm" bằng heuristics, để giữ tín hiệu hữu ích (Petrović & Ivanković, *State of Mutation Testing at Google*, ICSE-SEIP 2018).

### 5.2. Thí nghiệm: ba bộ test, một hàm nghiệp vụ

Thí nghiệm `t4` dùng một mutator AST tự viết (~60 dòng; công cụ thật cho Python là `mutmut` hoặc `cosmic-ray`). Nó đột biến ba hàm `mst_is_valid` (10/13 số, quy tắc chi nhánh), `line_tax` và `invoice_totals`, rồi chạy ba bộ test:

- **Điển hình**: 4 assert happy path, giống phần lớn codebase.
- **Ví dụ cẩn thận**: 11 assert, có sai chữ số kiểm tra, sai độ dài, ký tự lạ, chi nhánh `001`/`000`, số lẻ.
- **Thuộc tính**: 3 property-based test, mỗi cái 200–300 ví dụ.

| Bộ test | Điểm đột biến (25 đột biến, đã loại 6 tương đương) |
|---|---|
| Điển hình | **64%** |
| Ví dụ cẩn thận | **96%** |
| Thuộc tính | **100%** |

<!-- placeholder-mutation -->

<!-- fig:mutation -->
<figure markdown="span">
  ![Số đo thật: điểm đột biến của ba bộ test và những đột biến sống sót](assets/figures/12/mutation.light.svg#only-light){ loading=lazy }
  ![Số đo thật: điểm đột biến của ba bộ test và những đột biến sống sót](assets/figures/12/mutation.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 12.7 — Số đo thật: điểm đột biến của ba bộ test và những đột biến sống sót.</figcaption>
</figure>
<!-- /fig -->

Đột biến **duy nhất** sống sót qua bộ ví dụ cẩn thận là `ROUND_HALF_UP` → `ROUND_HALF_EVEN`, **đúng loại lỗi** mà mục 3.2 cài vào. Bộ ví dụ có 4 ca tính thuế nhưng không ca nào rơi vào trường hợp dư đúng 0,5. Còn bộ điển hình để sống 9 đột biến, phần lớn ở nhánh MST 13 số mà nó không bao giờ chạm tới, dù **độ phủ dòng của nó là 100%** với hàm `line_tax`.

Cách dùng thực tế: không cần đạt 100% trên toàn codebase. Chạy mutation testing **trên các mô-đun nghiệp vụ lõi** (tính tiền, thuế, kiểm MST, phân quyền) và **trên diff của PR**. Mỗi đột biến sống sót là một câu hỏi cụ thể: "nếu ai đó vô tình viết thế này, test có báo không?"

---

## 6. Hợp đồng API và tiến hóa: breaking change

### 6.1. Thế nào là breaking

Hợp đồng của `invoice-api` là OpenAPI của nó. 12.000 máy POS được tích hợp theo hợp đồng đó, và nhiều máy chạy phần mềm không được cập nhật trong nhiều năm. Một thay đổi là **breaking** nếu có client đang đúng hợp đồng cũ bị hỏng với server mới. Quy tắc nằm ở **chiều** của dữ liệu:

| Thay đổi | Request (client → server) | Response (server → client) |
|---|---|---|
| Thêm trường **tùy chọn** | an toàn | an toàn nếu client bỏ qua trường lạ |
| Thêm trường **bắt buộc** | **BREAKING** | an toàn |
| Bỏ trường | an toàn (server bỏ qua) | **BREAKING** |
| Thu hẹp ràng buộc (`maxLength`, `maximum`, bớt giá trị enum) | **BREAKING** | an toàn |
| Nới ràng buộc / thêm giá trị enum | an toàn | **BREAKING** (client cũ không biết giá trị mới) |
| Đổi kiểu, đổi tên, xóa endpoint | **BREAKING** | **BREAKING** |

Lưu ý điểm cuối: **thêm giá trị enum vào response là breaking**. Khi Nghị quyết thuế đưa thêm mức thuế suất mới và API bắt đầu trả `"vat_rate": "8"` cho các POS cũ, client nào `switch` không có nhánh `default` sẽ hỏng.

### 6.2. Thí nghiệm: tự động phát hiện trong CI

Thí nghiệm `t6` sinh OpenAPI từ hai phiên bản app FastAPI rồi chạy một bộ kiểm tra tối giản (cùng ý tưởng với các công cụ như `oasdiff`):

```text
BREAKING POST /v1/invoices body.buyer_tax_code: request thêm trường BẮT BUỘC
ok       POST /v1/invoices body.note: thêm trường tùy chọn (request)
BREAKING POST /v1/invoices body.lines[].vat_rate: request bỏ giá trị enum ['KCT']
BREAKING POST /v1/invoices body.lines[].name: request maxLength giảm 200 → 100
BREAKING POST /v1/invoices 201.issued_at: response bỏ trường
ok       POST /v1/invoices 201.currency: thêm trường tùy chọn (response)
BREAKING GET /v1/invoices/{invoice_id}/pdf: endpoint bị xóa
```

<!-- placeholder-breaking -->

<!-- fig:breaking -->
<figure markdown="span">
  ![Số đo thật: phát hiện breaking change giữa hai phiên bản OpenAPI do FastAPI sinh](assets/figures/12/breaking.light.svg#only-light){ loading=lazy }
  ![Số đo thật: phát hiện breaking change giữa hai phiên bản OpenAPI do FastAPI sinh](assets/figures/12/breaking.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 12.8 — Số đo thật: phát hiện breaking change giữa hai phiên bản OpenAPI do FastAPI sinh.</figcaption>
</figure>
<!-- /fig -->

Quy trình: CI sinh `openapi.json` từ nhánh PR, so với `openapi.json` của nhánh chính (lưu trong repo như một **artifact được review**), và **chặn merge** khi có BREAKING mà PR không gắn nhãn `api-breaking` có người duyệt. Đặt OpenAPI trong repo còn có tác dụng phụ tốt: mọi thay đổi hợp đồng hiện ra trong diff của PR, và reviewer thấy được.

### 6.3. Nghiên cứu: API ngoài thực tế tiến hóa ra sao

Nhóm của Cesare Pautasso (USI Lugano) khai thác hàng trăm nghìn đặc tả OpenAPI trên GitHub:

- Di Lauro, Serbout & Pautasso (**ECSA 2022**, *To Deprecate or to Simply Drop Operations?*) thấy trong 41.627 API chỉ **263 (0,6%)** có dùng đánh dấu `deprecated` cho operation. Phần lớn operation bị **xóa thẳng**, không báo trước.
- Serbout & Pautasso (**ICWE 2024**, *How Many Web APIs Evolve Following Semantic Versioning?*) phân tích 506.273 thay đổi trong 16.053 phiên bản của 3.075 API. Họ thấy **927 API** chưa từng có breaking change. Trong số API có breaking change, chỉ **517** luôn nâng phiên bản major khi làm vậy, còn **1.970 API** có lúc phát hành breaking change trong một bản minor hoặc patch, tức client không được báo trước.

Bài học cho `invoice-api`: đừng dựa vào kỷ luật. Hãy để **máy** kiểm tra breaking change, đánh dấu `deprecated=True` trên route/trường trước khi xóa, gửi header `Deprecation` (RFC 9745) và `Sunset` (RFC 8594), và theo dõi xem ai còn gọi endpoint cũ (Module 13) trước khi tắt.

---

## 7. Case Mekong Cloud: pipeline kiểm thử của `invoice-api`

<!-- placeholder-ci -->

<!-- fig:ci -->
<figure markdown="span">
  ![Pipeline kiểm thử của invoice-api trên mỗi pull request](assets/figures/12/ci.light.svg#only-light){ loading=lazy }
  ![Pipeline kiểm thử của invoice-api trên mỗi pull request](assets/figures/12/ci.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 12.9 — Pipeline kiểm thử của invoice-api trên mỗi pull request.</figcaption>
</figure>
<!-- /fig -->

| Giai đoạn | Chạy khi | Nội dung | Thời gian |
|---|---|---|---|
| Lint + kiểm kiểu | mỗi commit | `ruff`, `mypy --strict` (hoặc `pyright`) cho `app/` | ~20 s |
| Unit + thuộc tính | mỗi commit | quy tắc nghiệp vụ, model Pydantic, profile Hypothesis `ci` (500 ví dụ) | ~30 s |
| Tích hợp + DB | mỗi PR | Postgres container, savepoint rollback; ma trận BOLA/BFLA (Module 11) | ~1 phút |
| Đồng thời | mỗi PR (đánh dấu riêng) | idempotency 50 request trùng, cấp số 32 luồng (Module 10) | ~20 s |
| Hợp đồng | mỗi PR | `openapi.json` diff → chặn breaking; Schemathesis 50 ví dụ/endpoint | ~40 s |
| Mutation | mỗi PR, chỉ diff | đột biến dòng vừa sửa trong `app/domain/` | ~1–3 phút |
| Hằng đêm | 02:00 | Hypothesis `nightly`, Schemathesis stateful 1.000 ví dụ, mutation toàn bộ `domain/` | ~20 phút |

Kiểm tra kiểu tĩnh có mặt trong bảng vì nó rẻ nhất trong mọi loại "test": nó bắt sai kiểu ở ranh giới hàm trước khi chạy dòng nào. Pydantic đảm bảo **dữ liệu** đúng kiểu khi chạy, còn type checker đảm bảo **code** dùng dữ liệu đó đúng kiểu. Hai thứ bổ sung cho nhau, đúng như ý tưởng gradual typing ở Module 01.

---

## Lỗi thường gặp & cách xử lý

| Triệu chứng | Nguyên nhân gốc | Cách xử lý |
|---|---|---|
| `app.state.pool` là `None` trong test | `ASGITransport` không chạy lifespan | bọc bằng `app.router.lifespan_context(app)` |
| Test async treo hoặc "attached to a different loop" | trộn `TestClient` (loop riêng) với fixture async | dùng `AsyncClient` + `ASGITransport`; một event loop cho cả phiên test |
| Test lọt sang nhau, chạy riêng thì xanh, chạy chung thì đỏ | dữ liệu không được dọn; `dependency_overrides` không được xóa | savepoint rollback; fixture tự `clear()` override |
| Bộ test DB chạy mấy phút | tạo lại bảng hoặc TRUNCATE mỗi test | transaction + savepoint (4 ms/test) |
| Test idempotency luôn xanh dù code sai | chạy trong savepoint, một kết nối, không có tranh chấp thật | test đồng thời commit thật, nhiều kết nối, dọn bằng TRUNCATE |
| Test BFLA xanh dù thiếu `Security(scopes=...)` | override chính dependency đang được test | dùng token thật ký bằng khóa test |
| Hypothesis báo `Unsatisfiable` / `filter_too_much` | lọc quá nhiều input | viết strategy sinh trực tiếp dữ liệu hợp lệ (`@st.composite`) |
| Lỗi Hypothesis không tái hiện được trên máy khác | không lưu phản ví dụ | `@example(...)`; cache `.hypothesis/` trong CI |
| Schemathesis báo "accepted schema-violating request" | Pydantic lax ép kiểu (`false` → `0`) | `strict=True` hoặc `Strict*` cho trường quan trọng |
| Schemathesis báo "undocumented status code" | 400/401/413/429 không có trong OpenAPI | khai báo `responses=` cho route/router |
| Độ phủ 100% nhưng lỗi vẫn lọt | test chạy dòng code nhưng không kiểm kết quả | mutation testing cho mô-đun lõi |
| Client POS hỏng sau deploy | breaking change không bị phát hiện | diff OpenAPI trong CI; `deprecated` + `Sunset` trước khi xóa |

## Tóm tắt (cheat-sheet)

- **Tầng**: kiểm mỗi quy tắc ở tầng thấp nhất còn có nghĩa. Hàm thuần → unit + Hypothesis; route/DI → `AsyncClient` + `ASGITransport` (~0,3–0,5 ms/request); DB → Postgres thật + savepoint (~4 ms/test).
- **Lifespan**: `ASGITransport` không chạy lifespan → `app.router.lifespan_context(app)`.
- **Override** phần ở ngoài đối tượng cần test; test phân quyền bằng token thật.
- **Property-based**: round-trip, oracle, bất biến, phát hiện lỗi, idempotence. Strategy tự viết cho dữ liệu có ràng buộc. Profile `dev`/`ci`/`nightly`. Phản ví dụ → `@example`.
- **Schemathesis**: `--checks all`, chạy lại sau khi sửa (lỗi bị gom theo chữ ký); bắt cả lệch Pydantic lax ↔ OpenAPI và status code chưa khai báo.
- **Mutation testing**: đo test có **kiểm** hay không; chạy trên lõi nghiệp vụ và trên diff.
- **Breaking change**: request thêm bắt buộc / thu hẹp, response bỏ trường / thêm enum. Diff OpenAPI trong CI; `deprecated` + `Sunset`.

## Câu hỏi tự kiểm tra / phỏng vấn

**1.** Vì sao `TestClient` chậm hơn `AsyncClient` + `ASGITransport` khoảng 2,5 lần, và khi nào vẫn nên dùng nó?

<details markdown="1">
<summary>Đáp án</summary>

`TestClient` chạy app trong một event loop ở **luồng khác** (anyio portal), nên mỗi request phải chuyển luồng và đồng bộ hóa. `AsyncClient` + `ASGITransport` gọi app trực tiếp trong event loop của test. `TestClient` vẫn tiện cho test viết đồng bộ, cho WebSocket (`websocket_connect`), và khi muốn lifespan tự chạy trong khối `with`. Không trộn nó với fixture async dùng chung tài nguyên gắn với loop, ví dụ session asyncpg.

</details>

**2.** Giải thích cơ chế của fixture "transaction + savepoint". Vì sao code ứng dụng gọi `commit()` mà dữ liệu vẫn biến mất cuối test?

<details markdown="1">
<summary>Đáp án</summary>

Fixture mở một kết nối và một transaction ngoài cùng, rồi tạo `AsyncSession(bind=conn, join_transaction_mode="create_savepoint")`. Mọi `begin()`/`commit()` của session khi đó là `SAVEPOINT`/`RELEASE SAVEPOINT` bên trong transaction ngoài. Code thấy dữ liệu của chính nó như đã commit, nhưng transaction ngoài chưa bao giờ commit, và cuối test `rollback()` xóa tất cả. Hệ quả: không test được kịch bản cần nhiều kết nối thấy dữ liệu của nhau.

</details>

**3.** Viết một thuộc tính cho hàm `mst_is_valid` không cần oracle.

<details markdown="1">
<summary>Đáp án</summary>

"Phát hiện lỗi một chữ số": sinh 9 chữ số, tính chữ số kiểm tra (bỏ qua nếu ra 10), được MST hợp lệ $m$. Thuộc tính: (a) `mst_is_valid(m)` đúng; (b) với mọi vị trí $i$ và chữ số $d \ne m_i$, MST thay $m_i$ bằng $d$ là không hợp lệ. (b) đúng vì các trọng số đều khác 0 theo mod 11, nên đổi một chữ số luôn làm đổi tổng mod 11. Thêm: (c) chuỗi dài 9 hoặc 11 luôn không hợp lệ.

</details>

**4.** Test ví dụ `line_tax(27_500, 8) == 2_200` đúng cho cả bản dùng `round()` lẫn bản `ROUND_HALF_UP`. Tìm một input phân biệt hai bản, và giải thích vì sao Hypothesis tìm ra nó sau ~70 lần thử.

<details markdown="1">
<summary>Đáp án</summary>

Cần $\text{amount} \times \text{rate} / 100$ có phần lẻ đúng 0,5, và phần nguyên **chẵn** (half-even làm tròn xuống số chẵn). Ví dụ $(525, 10)$ → 52,5 → `round` = 52, half-up = 53. Với rate 10, cần amount tận cùng bằng 5 (xác suất 1/10). Với rate 5, cần amount ≡ 10 (mod 20) (xác suất 1/20). Với rate 8 thì không bao giờ xảy ra. Tính chung bốn mức thuế suất, khoảng 3,75% cặp cho phần lẻ 0,5, và một nửa trong số đó có phần nguyên chẵn, tức ~1/50. Kỳ vọng vài chục lần thử là gặp, khớp với 70 lần đo được. Sau đó Hypothesis shrink về cặp nhỏ nhất thỏa điều kiện.

</details>

**5.** Schemathesis báo "API accepted schema-violating request" với `"unit_price": false`. Đây có phải lỗi không? Sửa thế nào?

<details markdown="1">
<summary>Đáp án</summary>

Là lỗi hợp đồng. OpenAPI (sinh từ chính model) nói `integer`, nhưng Pydantic ở chế độ lax ép `false` → `0`. Client sai sẽ không bao giờ biết mình sai, và một hóa đơn có đơn giá 0 được tạo ra. Sửa: `ConfigDict(strict=True)` cho model request, hoặc `StrictInt` cho các trường tiền. Hoặc chấp nhận lax một cách có chủ đích và ghi rõ trong tài liệu.

</details>

**6.** Lần chạy Schemathesis đầu không báo lỗi `limit=0`, dù lỗi đó có thật. Vì sao?

<details markdown="1">
<summary>Đáp án</summary>

Schemathesis gom các lỗi có cùng chữ ký: cùng operation và cùng loại kiểm tra ("Server error" ở `GET /v1/invoices`). Lỗi sai schema (`limit=199` → 500) và lỗi chia cho 0 (`limit=0` → 500) có cùng chữ ký, nên chỉ một ví dụ được báo. Sau khi sửa lỗi kia, chạy lại thì lỗi `limit=0` hiện ra. Vì vậy: sửa và chạy lại tới khi sạch, đừng coi báo cáo đầu tiên là đầy đủ.

</details>

**7.** Một bộ test có độ phủ dòng 100% nhưng điểm đột biến 64%. Điều đó nói gì?

<details markdown="1">
<summary>Đáp án</summary>

Test **chạy** qua mọi dòng nhưng không **kiểm** đủ kết quả. Ví dụ: chỉ kiểm MST hợp lệ được chấp nhận, không kiểm MST sai bị từ chối; nhánh 13 số chạy qua với input không đặc trưng nên đổi `==` thành `!=` cũng không ai biết. Độ phủ là điều kiện cần, mutation score gần với điều kiện đủ hơn.

</details>

**8.** Đột biến `check < 10` → `check < 11` sống sót qua mọi bộ test. Có nên viết thêm test để diệt nó không?

<details markdown="1">
<summary>Đáp án</summary>

Không, vì đó là **đột biến tương đương**. `check = 10 - (x mod 11)` nằm trong khoảng 0..10. Với `check = 10`, điều kiện `int(s[9]) == check` không bao giờ đúng (một chữ số không thể bằng 10), nên `< 10` hay `< 11` cho cùng kết quả. Không test nào phân biệt được. Loại nó khỏi mẫu số, hoặc viết lại code cho tường minh hơn.

</details>

**9.** Phân loại breaking hay không: (a) thêm `"vat_rate": "KCT"` vào enum của **response**; (b) thêm trường tùy chọn `note` vào request; (c) đổi `buyer_name` thành `buyer_legal_name` trong request nhưng nhận cả hai qua `AliasChoices`.

<details markdown="1">
<summary>Đáp án</summary>

(a) **Breaking**: client cũ có thể không xử lý giá trị enum lạ. (b) An toàn. (c) An toàn với client gửi request, vì server vẫn nhận tên cũ (Module 10, expand/contract). Nhưng nếu response cũng đổi tên thì là breaking với phía đọc. Dùng `serialization_alias` để giữ tên cũ cho tới khi hết thời hạn deprecation.

</details>

**10.** Khi nào bạn **không** dùng property-based testing?

<details markdown="1">
<summary>Đáp án</summary>

Khi không tìm được thuộc tính có ý nghĩa nào ngoài "chạy lại chính code đó" (một oracle trùng với cài đặt chẳng kiểm được gì). Khi mỗi lần chạy rất đắt (gọi LLM thật, API bên thứ ba tính phí). Hoặc khi hành vi được định nghĩa bằng một bảng ví dụ cố định từ nghiệp vụ, ví dụ mẫu hóa đơn do cơ quan thuế quy định; lúc đó test bảng (parametrize) rõ ràng hơn. Property-based cũng không thay cho test hồi quy của lỗi đã biết: hãy giữ phản ví dụ bằng `@example`.

</details>

## Bài tập thực hành

1. **Round-trip mọi model.** Viết một test duyệt mọi model response của `invoice-api` (từ `app.openapi()` hoặc danh sách model) và kiểm `M.model_validate_json(m.model_dump_json()) == m` với dữ liệu sinh bởi `st.from_type(M)`. Có model nào hỏng không?
2. **Strict hay lax.** Bật `strict=True` cho `InvoiceIn`, chạy lại Schemathesis, và liệt kê những test hiện có bị hỏng. Quyết định giữ strict cho những trường nào.
3. **Mutation trên code của bạn.** Cài `mutmut`, chạy trên mô-đun tính tiền của Lab 03. Với mỗi đột biến sống sót: viết test diệt nó, hoặc ghi lý do nó tương đương.
4. **Chặn breaking change.** Thêm một job CI sinh `openapi.json` và so với bản trên nhánh chính bằng `oasdiff breaking` (hoặc mở rộng bộ kiểm trong `bench_testing.py`). Thử thêm một trường bắt buộc và xác nhận job đỏ.

## Tài liệu tham khảo

- K. Claessen, J. Hughes. *QuickCheck: A Lightweight Tool for Random Testing of Haskell Programs*. **ICFP 2000**.
- D. R. MacIver, Z. Hatfield-Dodds et al. *Hypothesis: A new approach to property-based testing*. **Journal of Open Source Software** 4(43), 2019.
- Z. Hatfield-Dodds, D. Dygalo. *Deriving Semantics-Aware Fuzzers from Web API Schemas*. **ICSE 2022** (poster). [arXiv:2112.10328](https://arxiv.org/abs/2112.10328)
- V. Atlidakis, P. Godefroid, M. Polishchuk. *RESTler: Stateful REST API Fuzzing*. **ICSE 2019**.
- A. Arcuri. *RESTful API Automated Test Case Generation with EvoMaster*. **ACM TOSEM** 28(1), 2019.
- A. Golmohammadi, M. Zhang, A. Arcuri. *Testing RESTful APIs: A Survey*. **ACM TOSEM** 33(1), 2023.
- R. A. DeMillo, R. J. Lipton, F. G. Sayward. *Hints on Test Data Selection: Help for the Practicing Programmer*. IEEE Computer 11(4), 1978.
- Y. Jia, M. Harman. *An Analysis and Survey of the Development of Mutation Testing*. **IEEE TSE** 37(5), 2011.
- G. Petrović, M. Ivanković. *State of Mutation Testing at Google*. **ICSE-SEIP 2018**.
- F. Di Lauro, S. Serbout, C. Pautasso. *To Deprecate or to Simply Drop Operations? An Empirical Study on the Evolution of a Large OpenAPI Collection*. **ECSA 2022**. [PDF](https://oas-search.inf.usi.ch/pdf/ecsa-2022.pdf)
- S. Serbout, C. Pautasso. *How Many Web APIs Evolve Following Semantic Versioning?* **ICWE 2024**. [PDF](https://design.inf.usi.ch/sites/default/files/biblio/apiace-icwe2024.pdf)
- E. Wilde. *RFC 8594 — The Sunset HTTP Header Field*. IETF, 2019.
- S. Dalal, E. Wilde. *RFC 9745 — The Deprecation HTTP Response Header Field*. IETF, 2025.
- M. Cohn. *Succeeding with Agile*. Addison-Wesley, 2009 (test pyramid).
- Tài liệu: [Hypothesis](https://hypothesis.readthedocs.io/), [Schemathesis](https://schemathesis.readthedocs.io/), [FastAPI — Testing](https://fastapi.tiangolo.com/tutorial/testing/), [FastAPI — Async tests](https://fastapi.tiangolo.com/advanced/async-tests/), [SQLAlchemy — Joining a Session into an External Transaction](https://docs.sqlalchemy.org/en/21/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites).
