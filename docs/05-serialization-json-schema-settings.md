# Module 05 — Serialization, JSON Schema & settings

> Thời lượng: ~45 phút · Mức độ: Trung bình · Tiên quyết: Module 03, Module 04

Validation là nửa đầu của hợp đồng dữ liệu: dữ liệu **đi vào**. Nửa sau là dữ liệu **đi ra** — response gửi cho máy POS, sự kiện ghi vào hàng đợi, bản ghi audit, và tài liệu mô tả hợp đồng đó cho người khác (JSON Schema, OpenAPI). Module này đi qua ba chủ đề nối với nhau bằng cùng một ý: **một định nghĩa model, nhiều biểu diễn**. Serialization biến model thành JSON đúng định dạng đã hứa; JSON Schema biến model thành tài liệu máy đọc được; `pydantic-settings` dùng chính cỗ máy validate cho cấu hình của service. Ở cuối, một thí nghiệm cho thấy JSON Schema chỉ là **xấp xỉ** của validator Pydantic — và xấp xỉ ở những chỗ nào.

Mọi hành vi được chạy thật với Pydantic 2.14.1 và pydantic-settings 2.15.

## Mục tiêu học tập

Sau module này, bạn có thể:

1. Dùng `model_dump` / `model_dump_json` với các chế độ `python`/`json` và các tùy chọn `include`, `exclude`, `exclude_unset`, `exclude_none`, `by_alias`; biết kiểu nào đổi biểu diễn khi sang JSON (`Decimal`, `datetime`, `SecretStr`).
2. Viết serializer tùy biến (`field_serializer`, `PlainSerializer`, `model_serializer`) và `computed_field`, và giải thích bẫy round-trip của computed field với `extra="forbid"`.
3. Thiết kế alias cho API dùng camelCase và dữ liệu cũ (`alias_generator`, `validation_alias`, `AliasChoices`, `AliasPath`).
4. Đọc JSON Schema do Pydantic sinh ra, phân biệt **schema validation và schema serialization**, và biết những gì JSON Schema **không** diễn tả được.
5. Thiết lập cấu hình service bằng `pydantic-settings` với thứ tự ưu tiên nguồn, biến lồng nhau, file secret và `SecretStr`.
6. So sánh chi phí các cách serialize bằng số đo thật.

---

## 1. Serialization: một model, nhiều biểu diễn

### 1.1. Hai chế độ

```python
from decimal import Decimal
from pydantic import BaseModel, SecretStr
from datetime import datetime, timezone

class Inv(BaseModel):
    issued_at: datetime
    total: Decimal
    api_key: SecretStr

i = Inv(issued_at=datetime(2026, 10, 13, 4, 45, tzinfo=timezone.utc), total=Decimal("118007"), api_key="s3cr3t")
i.model_dump()               # chế độ python: giữ object Python
# {'issued_at': datetime(...), 'total': Decimal('118007'), 'api_key': SecretStr('**********')}
i.model_dump(mode="json")    # chế độ json: chỉ còn kiểu JSON (str, int, float, bool, None, list, dict)
i.model_dump_json()          # chuỗi JSON, serialize thẳng trong Rust
# {"issued_at":"2026-10-13T04:45:00Z","total":"118007","api_key":"**********"}
```

Ba điều cần nhớ về biểu diễn JSON:

- **`Decimal` thành chuỗi** (`"118007"`, `"1.5"`), không thành số. Đây là lựa chọn đúng: số JSON thường bị client đọc thành float 64-bit và mất chính xác (Module 01, thí nghiệm orjson với $2^{64}$). Nếu client cần số, phải quyết định có chủ đích (`PlainSerializer` hoặc dùng `int` VND).
- **`datetime` thành ISO 8601**, giữ múi giờ của giá trị. Muốn mọi thời điểm ra theo giờ Việt Nam, viết serializer (mục 1.3).
- **`SecretStr` thành `"**********"`** ở cả hai chế độ. Muốn lấy giá trị thật phải gọi `.get_secret_value()` tường minh — một cơ chế chống lộ bí mật vào log và response.

### 1.2. Chọn trường: `include`, `exclude`, `exclude_*`

| Tùy chọn | Bỏ trường khi | Dùng cho |
|---|---|---|
| `exclude={"buyer": {"email"}}` | luôn (lồng nhau được) | ẩn trường nhạy cảm trong một ngữ cảnh cụ thể |
| `exclude_unset=True` | client **không gửi** | `PATCH`: chỉ cập nhật trường được gửi (Module 03, mục 6) |
| `exclude_defaults=True` | giá trị bằng mặc định | nén payload |
| `exclude_none=True` | giá trị là `None` | API không muốn trả `null` |

Trong FastAPI, cách đúng để kiểm soát trường đi ra là **model response riêng** (`InvoiceOut`) chứ không phải `exclude` rải rác — lý do bảo mật (BOPLA) ở Module 07 và 11. `exclude` hợp cho log và audit.

<!-- placeholder-dump-modes -->

<!-- fig:dump-modes -->
<figure markdown="span">
  ![Ba biểu diễn của cùng một model; Decimal, datetime và SecretStr đổi dạng khi sang JSON](assets/figures/05/dump-modes.light.svg#only-light){ loading=lazy }
  ![Ba biểu diễn của cùng một model; Decimal, datetime và SecretStr đổi dạng khi sang JSON](assets/figures/05/dump-modes.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 5.1 — Ba biểu diễn của cùng một model; Decimal, datetime và SecretStr đổi dạng khi sang JSON.</figcaption>
</figure>
<!-- /fig -->

### 1.3. Serializer tùy biến

```python
from datetime import timedelta, timezone
from typing import Annotated
from pydantic import PlainSerializer, field_serializer

VN = timezone(timedelta(hours=7))

class InvoiceOut(BaseModel):
    issued_at: datetime

    @field_serializer("issued_at")
    def _vn_time(self, v: datetime) -> str:          # luôn trả giờ Việt Nam
        return v.astimezone(VN).isoformat()

# Kiểu tái sử dụng: chỉ đổi biểu diễn khi ra JSON, giữ int ở chế độ python
VNDText = Annotated[int, PlainSerializer(lambda v: f"{v:,}".replace(",", "."), return_type=str, when_used="json")]

class Receipt(BaseModel):
    total: VNDText

Receipt(total=118007).model_dump()        # {'total': 118007}
Receipt(total=118007).model_dump_json()   # {"total":"118.007"}
```

`when_used="json"` là chi tiết quan trọng: code Python nội bộ vẫn thấy `int` để tính toán; chỉ biểu diễn ra ngoài đổi. `model_serializer` (cả model) dùng khi hình dạng output khác hẳn hình dạng model — ví dụ xuất định dạng XML/JSON của cơ quan thuế.

### 1.4. `computed_field` và bẫy round-trip

```python
from pydantic import computed_field

class LineOut(BaseModel):
    quantity: Decimal
    unit_price: int

    @computed_field
    @property
    def amount(self) -> int:
        return half_up(self.quantity * self.unit_price)   # half_up: Module 04
```

`amount` xuất hiện trong `model_dump()` và trong **JSON Schema chế độ serialization**, nhưng không phải là trường đầu vào. Bẫy kiểm chứng được: nếu model có `extra="forbid"`, thì

```python
LineOut.model_validate_json(x.model_dump_json())
# ValidationError: ('amount',) extra_forbidden
```

— dữ liệu chính mình xuất ra không đọc lại được, vi phạm tính chất round-trip của Module 01. Cách xử lý: tách model vào/ra (`LineIn` không có computed field, `LineOut` có), hoặc khi đọc lại thì `exclude` các computed field. Đây là một lý do nữa để **tách model request và response** ngay từ đầu.

<!-- placeholder-roundtrip -->

<!-- fig:roundtrip -->
<figure markdown="span">
  ![Computed field có mặt trong output nên model có extra='forbid' không đọc lại được dữ liệu chính nó xuất ra; tách model vào/ra để tránh](assets/figures/05/roundtrip.light.svg#only-light){ loading=lazy }
  ![Computed field có mặt trong output nên model có extra='forbid' không đọc lại được dữ liệu chính nó xuất ra; tách model vào/ra để tránh](assets/figures/05/roundtrip.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 5.2 — Computed field có mặt trong output nên model có extra='forbid' không đọc lại được dữ liệu chính nó xuất ra; tách model vào/ra để tránh.</figcaption>
</figure>
<!-- /fig -->

---

## 2. Alias: tên trong Python khác tên trên dây

### 2.1. API camelCase, code snake_case

```python
from pydantic import ConfigDict
from pydantic.alias_generators import to_camel

class LineIn(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, validate_by_name=True,
                              validate_by_alias=True, serialize_by_alias=True)
    line_no: int
    unit_price: int

LineIn.model_validate({"lineNo": 1, "unitPrice": 27500})   # nhận camelCase
LineIn.model_validate({"line_no": 1, "unit_price": 27500}) # vẫn nhận snake_case (validate_by_name)
LineIn(line_no=1, unit_price=27500).model_dump()           # {'lineNo': 1, 'unitPrice': 27500}
```

Ba cờ cấu hình (từ Pydantic 2.11) tách bạch: nhận theo alias, nhận theo tên, xuất theo alias. Mặc định Pydantic **chỉ nhận alias** và **xuất theo tên** — dễ gây bất đối xứng; với API công khai mình khuyên đặt cả ba như trên và giữ **một** quy ước tên trên dây.

### 2.2. Dữ liệu cũ: nhiều tên, đường dẫn lồng

```python
from pydantic import AliasChoices, AliasPath, Field

class LegacySeller(BaseModel):
    tax_code: str = Field(validation_alias=AliasChoices("taxCode", "mst", AliasPath("seller", "tax_code")))

LegacySeller.model_validate({"mst": "0100233488"})
LegacySeller.model_validate({"seller": {"tax_code": "0100233488"}})
```

`AliasChoices` thử lần lượt các tên; `AliasPath` đọc từ đường dẫn lồng. Dùng để nhận định dạng của hệ thống cũ **mà không làm bẩn** model mới — trên dây ra vẫn chỉ có một tên.

<!-- placeholder-alias -->

<!-- fig:alias -->
<figure markdown="span">
  ![AliasChoices và AliasPath cho phép nhận nhiều tên trên dây nhưng chỉ xuất một tên](assets/figures/05/alias.light.svg#only-light){ loading=lazy }
  ![AliasChoices và AliasPath cho phép nhận nhiều tên trên dây nhưng chỉ xuất một tên](assets/figures/05/alias.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 5.3 — AliasChoices và AliasPath cho phép nhận nhiều tên trên dây nhưng chỉ xuất một tên.</figcaption>
</figure>
<!-- /fig -->

---

## 3. JSON Schema: hợp đồng máy đọc được

### 3.1. Sinh schema

```python
schema = InvoiceIn.model_json_schema()                    # mặc định mode="validation"
schema_out = InvoiceOut.model_json_schema(mode="serialization")
```

Pydantic sinh JSON Schema theo **Draft 2020-12**: model con vào `$defs`, tham chiếu bằng `$ref`; ràng buộc `Field` thành từ khóa tương ứng (`minimum`/`exclusiveMinimum`, `minLength`/`maxLength`, `pattern`, `enum`/`const` cho `Literal`); `extra="forbid"` thành `additionalProperties: false`; `SecretStr` thành `format: password` + `writeOnly: true`; discriminated union thành `oneOf` + `discriminator`. FastAPI ghép các schema này vào tài liệu **OpenAPI 3.1** (Module 07).

### 3.2. Validation schema khác serialization schema

Kiểm chứng với `LineIn` có alias và `amount` là computed field:

| | `required` |
|---|---|
| `mode="validation"` | `["lineNo", "unitPrice", "quantity"]` — `note` có mặc định nên không bắt buộc; không có `amount` |
| `mode="serialization"` | `["lineNo", "unitPrice", "quantity", "amount"]` — computed field luôn có mặt trong output |

Hai chế độ mô tả hai câu hỏi khác nhau: *"client phải gửi gì?"* và *"server chắc chắn trả về gì?"*. Trình sinh code phía client cần đúng cái thứ hai cho kiểu response. Một ví dụ khác: `Decimal` ở chế độ validation là `anyOf: [number, string]` (nhận cả hai), ở serialization là `string` (luôn xuất chuỗi).

<!-- placeholder-schema-modes -->

<!-- fig:schema-modes -->
<figure markdown="span">
  ![Cùng một model, hai JSON Schema: những gì client phải gửi và những gì server chắc chắn trả về](assets/figures/05/schema-modes.light.svg#only-light){ loading=lazy }
  ![Cùng một model, hai JSON Schema: những gì client phải gửi và những gì server chắc chắn trả về](assets/figures/05/schema-modes.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 5.4 — Cùng một model, hai JSON Schema: những gì client phải gửi và những gì server chắc chắn trả về.</figcaption>
</figure>
<!-- /fig -->

### 3.3. Nền tảng hình thức và giới hạn

JSON Schema từng là bản thảo không có định nghĩa hình thức thống nhất; Pezoa, Reutter, Suárez, Ugarte và Vrgoč (WWW 2016, *Foundations of JSON Schema*) đưa ra định nghĩa hình thức đầu tiên về cú pháp và ngữ nghĩa, chỉ ra các validator thời đó **không đồng ý với nhau** ở các trường hợp mơ hồ, và phân tích độ phức tạp của bài toán validate. Các thế hệ đặc tả sau (Draft 2019-09, 2020-12) làm rõ nhiều chỗ, nhưng hai giới hạn cơ bản vẫn còn:

1. **JSON Schema không diễn tả được quy tắc liên trường có tính toán** — "tổng = Σ dòng", checksum MST, "`line_no` không trùng". Chúng là quy tắc tầng 3 (Module 01) nằm ngoài sức biểu đạt của các từ khóa cấu trúc.
2. **`format` mặc định chỉ là chú thích** (annotation) trong Draft 2020-12: một validator tuân chuẩn có thể bỏ qua `format: date-time`.

### 3.4. Thí nghiệm: schema có khớp với validator không?

Lấy một hóa đơn hợp lệ, áp 13 loại đột biến, mỗi loại 40 lần. Mỗi biến thể được kiểm tra bằng thư viện `jsonschema` (Draft 2020-12, có bật format checker) với schema do Pydantic sinh ra từ `InvoiceIn` v2 (Module 04), và bằng chính `InvoiceIn` ở hai chế độ lax và strict (script `scripts/bench/bench_schema_diff.py`):

| Đột biến | Schema | Pydantic lax | Pydantic strict |
|---|---|---|---|
| không đột biến | nhận | nhận | nhận |
| trường lạ, thiếu trường, thuế suất lạ, số lượng âm | từ chối | từ chối | từ chối |
| số → chuỗi số (`"1024"`) | từ chối | **nhận** | từ chối |
| int → float `.0` (`1024.0`) | **nhận** | nhận | **từ chối** |
| MST có dấu gạch (`0314409058-002`) | nhận | nhận (chuẩn hóa) | nhận |
| MST sai checksum, `amount` dòng sai, lệch tổng 1 đồng, `line_no` trùng | **nhận** | từ chối | từ chối |
| ngày không múi giờ | **nhận** | từ chối | từ chối |

<!-- placeholder-schema-diff -->

<!-- fig:schema-diff -->
<figure markdown="span">
  ![Kết quả thí nghiệm mục 3](assets/figures/05/schema-diff.light.svg#only-light){ loading=lazy }
  ![Kết quả thí nghiệm mục 3](assets/figures/05/schema-diff.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 5.5 — Kết quả thí nghiệm mục 3.4: JSON Schema bỏ sót mọi quy tắc tầng 3, còn chế độ lax nhận những chuỗi số mà schema từ chối.</figcaption>
</figure>
<!-- /fig -->

Đọc kết quả:

- **Schema lỏng hơn validator** ở mọi quy tắc tầng 3 (checksum, tổng, trùng) — đúng như lý thuyết dự đoán. Client chỉ validate bằng schema sẽ vẫn bị server từ chối; tài liệu API phải nói rõ các quy tắc này bằng lời.
- **Lax lỏng hơn schema** ở chuyển đổi kiểu (`"1024"`): schema nói `integer`, server lax vẫn nhận. Nếu dùng lax, tài liệu đang **nói dối theo hướng an toàn**.
- **Schema lỏng hơn strict** ở `1024.0`: JSON Schema coi số có phần thập phân bằng 0 là `integer`, Pydantic strict thì không.
- **Ngày không múi giờ** lọt qua schema vì bộ kiểm tra `date-time` của `jsonschema` cần gói phụ (`rfc3339-validator`); không có nó, `format` bị bỏ qua — minh họa cho giới hạn 2 ở trên.

Bài học thực dụng: **nguồn sự thật là model Pydantic**, JSON Schema/OpenAPI là bản chiếu có mất mát. Dùng schema để sinh code client và kiểm tra cấu trúc sớm; dùng server để quyết định cuối cùng; và bổ sung `description`/`examples` cho những quy tắc schema không chở được.

### 3.5. Làm giàu schema

```python
class InvoiceIn(RequestModel):
    model_config = ConfigDict(json_schema_extra={
        "examples": [{"series": "1C26TMK", "number": 1024, "...": "..."}]})
    total_tax: VND = Field(description="Tổng thuế = Σ làm tròn half-up(amount × thuế suất) của từng dòng")
```

`description` trên trường, `examples` trên model, `title` cho tên hiển thị, `__get_pydantic_json_schema__` cho kiểu tùy biến (Module 04). FastAPI đưa tất cả vào trang `/docs`.

---

## 4. Chi phí serialization: số đo thật

Serialize một hóa đơn đã validate theo năm cách (trung vị của 7 lần lặp, 1 core, script `bench_misc.py`):

| Cách | 1 dòng | 12 dòng | 200 dòng |
|---|---|---|---|
| `model_dump()` (dict Python) | 3,4 µs | 13,7 µs | 170 µs |
| `model_dump_json()` (Rust thẳng ra JSON) | 5,2 µs | **14,9 µs** | 184 µs |
| `model_dump(mode="json")` + `orjson.dumps` | 4,8 µs | 21,8 µs | 200 µs |
| `model_dump()` + `json.dumps(default=str)` | 12,9 µs | 41,6 µs | 446 µs |
| `msgspec.json.encode` (Struct) | 0,9 µs | 3,3 µs | 43 µs |

<!-- placeholder-ser-cost -->

<!-- fig:ser-cost -->
<figure markdown="span">
  ![Số đo thật: chi phí serialize theo số dòng hàng của năm cách làm](assets/figures/05/ser-cost.light.svg#only-light){ loading=lazy }
  ![Số đo thật: chi phí serialize theo số dòng hàng của năm cách làm](assets/figures/05/ser-cost.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 5.6 — Số đo thật: chi phí serialize theo số dòng hàng của năm cách làm.</figcaption>
</figure>
<!-- /fig -->

- `model_dump_json()` gần như bằng chi phí dựng dict Python — vì nó **không** dựng dict, nó đi thẳng từ object sang byte trong Rust. Đường `model_dump()` + `json.dumps` chậm ~2,8 lần và còn phải tự xử lý `Decimal`/`datetime`.
- msgspec nhanh hơn ~4,5 lần nhờ thiết kế đơn giản hơn (Struct không có validator Python, serializer tùy biến). Module 06 bàn khi nào sự chênh lệch này đáng để đổi thư viện.
- Đường lỗi cũng có giá: tạo `ValidationError` với 24 lỗi rồi gọi `.json()` mất ~53 µs so với ~24 µs cho payload hợp lệ — payload sai tốn gấp đôi. Đáng nhớ khi nghĩ về tấn công cố tình gửi payload lỗi (Module 11).

---

## 5. `pydantic-settings`: cấu hình là dữ liệu ở ranh giới

### 5.1. Vấn đề

Biến môi trường, file `.env`, secret mount từ Kubernetes — cấu hình cũng là **dữ liệu từ bên ngoài**, cũng toàn là chuỗi, cũng có thể sai. Service khởi động với `DB_POOL_SIZE=twenty` hay `JWT_SECRET` rỗng nên **chết ngay khi khởi động** với lỗi rõ ràng, không phải chạy rồi hỏng lúc 2 giờ sáng. Nguyên tắc 12-factor (cấu hình qua môi trường) + parse ở ranh giới (Module 01) = `pydantic-settings`.

### 5.2. Cấu hình của `invoice-api`

```python
from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class DB(BaseModel):
    url: str = "postgresql+asyncpg://localhost/invoices"
    pool_size: int = 10

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INVOICE_", env_nested_delimiter="__",
                                      env_file=".env", secrets_dir="/run/secrets")
    env: str = "dev"
    jwt_secret: SecretStr                  # bắt buộc: thiếu là không khởi động
    db: DB = DB()
    allowed_origins: list[str] = []

settings = Settings()                       # parse + validate một lần, lúc khởi động
```

### 5.3. Thứ tự ưu tiên nguồn (kiểm chứng)

Thí nghiệm: đặt `INVOICE_DB__POOL_SIZE=15` trong `.env`, `=20` trong biến môi trường; `INVOICE_JWT_SECRET` có trong `.env` và trong file `secrets/invoice_jwt_secret`:

| Nguồn | Ưu tiên | Kết quả quan sát |
|---|---|---|
| tham số khởi tạo `Settings(env="prod")` | 1 (cao nhất) | `env == "prod"` |
| biến môi trường | 2 | `pool_size == 20` (thắng `.env`) |
| file `.env` | 3 | khi xóa biến môi trường: `pool_size == 15`; `jwt_secret` lấy từ `.env` |
| thư mục secrets | 4 | khi xóa `.env`: `jwt_secret` lấy từ file secret |
| giá trị mặc định | 5 | — |

<!-- placeholder-settings -->

<!-- fig:settings -->
<figure markdown="span">
  ![Thứ tự ưu tiên nguồn cấu hình, mỗi bậc kèm kết quả quan sát được trong thí nghiệm](assets/figures/05/settings.light.svg#only-light){ loading=lazy }
  ![Thứ tự ưu tiên nguồn cấu hình, mỗi bậc kèm kết quả quan sát được trong thí nghiệm](assets/figures/05/settings.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 5.7 — Thứ tự ưu tiên nguồn cấu hình, mỗi bậc kèm kết quả quan sát được trong thí nghiệm.</figcaption>
</figure>
<!-- /fig -->

Ghi chú vận hành:

- `env_nested_delimiter="__"` cho phép `INVOICE_DB__POOL_SIZE` điền vào `settings.db.pool_size`; kiểu phức (`list[str]`) đọc từ chuỗi JSON (`'["https://pos.mekong.example"]'`).
- `repr(settings)` hiển thị `jwt_secret=SecretStr('**********')` — log cấu hình lúc khởi động là an toàn.
- Trên Kubernetes, secret mount thành file → `secrets_dir`; biến môi trường cho cấu hình không nhạy cảm. Không nhét secret vào image hay `.env` commit vào git.
- Tạo `Settings()` **một lần** (cấp module hoặc trong lifespan) và truyền qua dependency (Module 08) — test có thể override.

---

## 6. Case Mekong Cloud: tách model vào và ra

Tổng hợp các quyết định của module thành một bộ model cho `invoice-api`:

```python
class InvoiceIn(RequestModel): ...                 # Module 04: strict, extra="forbid", đủ tầng 1–3

class LineOut(BaseModel):
    line_no: int
    name: str
    quantity: Decimal                              # ra JSON là chuỗi: không mất chính xác
    unit_price: int
    vat_rate: VatRate
    amount: int
    tax: int

class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # tạo từ row ORM (Module 10)
    id: UUID
    series: str
    number: int
    seller_tax_code: str
    issued_at: datetime
    status: Literal["draft", "issued", "sent_to_tax_authority", "adjusted", "replaced"]
    lines: list[LineOut]
    total_before_tax: int
    total_tax: int
    total: int
    lookup_code: str                               # mã tra cứu cho người mua

    @field_serializer("issued_at")
    def _vn_time(self, v: datetime) -> str:
        return v.astimezone(VN).isoformat()
```

- `InvoiceIn` không có `id`, `status`, `lookup_code` → client **không thể** đặt chúng (chống mass assignment, Module 11).
- `InvoiceOut` không có trường nội bộ (`tenant_id`, `created_by`, chữ ký số thô) → không thể lộ ra ngoài dù ORM row có.
- Thời điểm luôn ra theo giờ Việt Nam; tiền là `int`, số lượng là chuỗi thập phân.
- Hai model có hai JSON Schema: OpenAPI cho thấy chính xác client gửi gì và nhận gì.

<!-- placeholder-in-out -->

<!-- fig:in-out -->
<figure markdown="span">
  ![Ba hình dạng của một hóa đơn: model đầu vào, hàng ORM và model đầu ra](assets/figures/05/in-out.light.svg#only-light){ loading=lazy }
  ![Ba hình dạng của một hóa đơn: model đầu vào, hàng ORM và model đầu ra](assets/figures/05/in-out.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 5.8 — Ba hình dạng của một hóa đơn: model đầu vào, hàng ORM và model đầu ra.</figcaption>
</figure>
<!-- /fig -->

---

## Lỗi thường gặp & cách xử lý

| Triệu chứng | Nguyên nhân gốc | Cách xử lý |
|---|---|---|
| Client JavaScript nhận tổng tiền sai lệch ở hàng đơn vị | Xuất `Decimal`/số lớn thành số JSON → float 64-bit | Giữ mặc định xuất `Decimal` thành chuỗi; tiền VND là `int` < $2^{53}$ |
| Dữ liệu tự xuất ra không đọc lại được | `computed_field` + `extra="forbid"` | Tách model in/out, hoặc exclude computed khi đọc lại |
| API nhận camelCase nhưng trả snake_case | Mặc định xuất theo tên trường | `serialize_by_alias=True` (hoặc `by_alias=True`) |
| Response lộ trường nội bộ | Trả thẳng ORM row/model nội bộ | Model response riêng, chỉ có trường công khai |
| Client sinh code thấy trường response là optional dù luôn có | Dùng schema validation cho response | Dùng `mode="serialization"` (FastAPI làm đúng cho `response_model`) |
| Validate bằng JSON Schema ở client qua, server vẫn 422 | Quy tắc tầng 3 không biểu diễn được bằng schema | Ghi quy tắc trong `description`; coi server là nguồn sự thật |
| Service chạy với cấu hình sai, hỏng giữa chừng | Đọc `os.environ` rải rác, không validate | `BaseSettings` tạo một lần lúc khởi động; trường bắt buộc không mặc định |
| Secret xuất hiện trong log | Log `dict` cấu hình thô | `SecretStr`; log `repr(settings)` |

## Tóm tắt (cheat-sheet)

- `model_dump()` (Python) · `model_dump(mode="json")` · `model_dump_json()` (nhanh nhất, Rust thẳng ra byte).
- JSON: `Decimal` → chuỗi, `datetime` → ISO 8601, `SecretStr` → `**********`.
- `exclude_unset` cho PATCH; model response riêng thay vì `exclude` rải rác.
- Serializer: `field_serializer`, `PlainSerializer(..., when_used="json")`, `model_serializer`; `computed_field` có trong output và schema serialization — cẩn thận round-trip với `extra="forbid"`.
- Alias: `alias_generator=to_camel` + `validate_by_name` + `validate_by_alias` + `serialize_by_alias`; dữ liệu cũ: `AliasChoices`, `AliasPath`.
- JSON Schema 2020-12: validation ≠ serialization; không diễn tả được quy tắc tầng 3; `format` chỉ là chú thích. Thí nghiệm: schema nhận hóa đơn sai tổng/sai checksum; lax nhận `"1024"` mà schema từ chối.
- Chi phí (12 dòng): `model_dump_json` ~15 µs, `model_dump`+`json.dumps` ~42 µs, msgspec ~3 µs.
- Settings: init > env > `.env` > secrets dir > default; `env_nested_delimiter`; `SecretStr`; tạo một lần.

## Câu hỏi tự kiểm tra / phỏng vấn

1. Vì sao Pydantic xuất `Decimal` thành chuỗi JSON? Khi nào nên đổi?

    <details markdown="1"><summary>Gợi ý</summary>
    Số JSON thường được đọc thành float 64-bit (JavaScript `Number`), mất chính xác với số thập phân và số lớn. Chuỗi giữ nguyên giá trị. Chỉ đổi sang số khi chắc chắn client parse số chính xác, hoặc dùng `int` đơn vị nhỏ nhất (VND) và biết nó < $2^{53}$.
    </details>

2. `exclude_unset`, `exclude_defaults`, `exclude_none` khác nhau thế nào? Cái nào cho PATCH?

    <details markdown="1"><summary>Gợi ý</summary>
    Unset: client không gửi trường; defaults: giá trị bằng mặc định (dù có gửi); none: giá trị là None. PATCH dùng `exclude_unset` (hoặc sentinel `MISSING`) để phân biệt "không gửi" với "gửi null".
    </details>

3. Mô tả bẫy round-trip của `computed_field`. Hai cách sửa?

    <details markdown="1"><summary>Gợi ý</summary>
    Computed field có trong output; khi đọc lại bằng model `extra="forbid"`, nó thành trường lạ → lỗi. Sửa: tách model vào/ra; hoặc `exclude` computed field trước khi đọc lại (hoặc `extra="ignore"` cho model đọc lại).
    </details>

4. Schema chế độ validation và serialization của cùng một model khác nhau ở đâu? Cho hai ví dụ.

    <details markdown="1"><summary>Gợi ý</summary>
    (1) Trường có mặc định: không bắt buộc khi validate, nhưng luôn có mặt khi serialize. (2) Computed field chỉ có ở serialization. (3) `Decimal`: validation `anyOf[number,string]`, serialization `string`.
    </details>

5. Kể ba loại quy tắc mà JSON Schema không diễn tả được nhưng Pydantic validate được.

    <details markdown="1"><summary>Gợi ý</summary>
    Checksum (MST); bất biến liên trường có tính toán (tổng = Σ dòng, amount = qty × price); tính duy nhất theo một khóa trong mảng object (`line_no` không trùng — `uniqueItems` chỉ so cả phần tử).
    </details>

6. Trong thí nghiệm mục 3.4, ô "schema nhận / Pydantic strict từ chối" xuất hiện ở đột biến nào và vì sao?

    <details markdown="1"><summary>Gợi ý</summary>
    `1024.0` cho trường integer: JSON Schema 2020-12 coi số có phần thập phân 0 là integer; Pydantic strict yêu cầu số nguyên JSON thực sự. Cùng với các quy tắc tầng 3 và ngày thiếu múi giờ (format không được kiểm).
    </details>

7. Thứ tự ưu tiên nguồn cấu hình của pydantic-settings? Bạn đặt `JWT_SECRET` ở đâu trên Kubernetes?

    <details markdown="1"><summary>Gợi ý</summary>
    Tham số khởi tạo > biến môi trường > `.env` > thư mục secrets > mặc định. JWT secret: Kubernetes Secret mount thành file và đọc qua `secrets_dir` (hoặc biến môi trường lấy từ Secret); không đặt trong image hay `.env` commit.
    </details>

8. Vì sao nên có hai model `InvoiceIn` và `InvoiceOut` thay vì một model `Invoice` với nhiều trường optional?

    <details markdown="1"><summary>Gợi ý</summary>
    Bảo mật (client không đặt được `id`, `status`; response không lộ trường nội bộ), schema chính xác cho từng chiều, tránh bẫy computed field/round-trip, và mỗi model có cấu hình riêng (strict/forbid cho vào; from_attributes cho ra).
    </details>

## Bài tập thực hành

1. **Serializer giờ Việt Nam (CPU, 10 phút).** Viết kiểu `VNDateTime = Annotated[AwareDatetime, PlainSerializer(...)]` luôn xuất `+07:00`; kiểm tra round-trip (`parse(dump(x)) == x` theo thời điểm tuyệt đối).
2. **Thí nghiệm schema (CPU, 20 phút).** Chạy `bench_schema_diff.py`; cài `rfc3339-validator` rồi chạy lại — đột biến "ngày không múi giờ" đổi ô nào? Thêm 3 đột biến mới của riêng bạn.
3. **Settings cho `ai-gateway` (CPU, 15 phút).** Viết `Settings` có `llm_base_url: AnyHttpUrl`, `llm_api_key: SecretStr`, `llm_timeout_s: float = 30` với ràng buộc `gt=0, le=120`, `zendesk.subdomain`, `zendesk.token`. Viết test xác nhận service không khởi động khi thiếu `llm_api_key`.
4. **Đo serialization (CPU, 10 phút).** Chạy `bench_misc.py --only ser` trên máy bạn; so tỷ lệ `model_dump_json` / (`model_dump` + `json.dumps`) với số trong bài.

## Tài liệu tham khảo

Paper:

- Pezoa, F., Reutter, J. L., Suárez, F., Ugarte, M., Vrgoč, D. (2016). *Foundations of JSON Schema*. WWW 2016, pp. 263–273. DOI 10.1145/2872427.2883029. https://dvrgoc.ing.uc.cl/data/json.pdf
- Bourhis, P., Reutter, J. L., Suárez, F., Vrgoč, D. (2017). *JSON: data model, query languages and schema specification*. PODS 2017. arXiv:1701.02221.

Tiêu chuẩn và tài liệu chính thức (tra cứu 10/2026):

- JSON Schema — *Draft 2020-12* (Core, Validation). https://json-schema.org/draft/2020-12
- OpenAPI Specification 3.1. https://spec.openapis.org/oas/v3.1.0
- Pydantic — *Serialization*. https://docs.pydantic.dev/latest/concepts/serialization/
- Pydantic — *JSON Schema*. https://docs.pydantic.dev/latest/concepts/json_schema/
- Pydantic — *Alias*. https://docs.pydantic.dev/latest/concepts/alias/
- Pydantic — *Fields: computed fields*. https://docs.pydantic.dev/latest/concepts/fields/
- pydantic-settings — *Settings Management*. https://docs.pydantic.dev/latest/concepts/pydantic_settings/
- python-jsonschema. https://python-jsonschema.readthedocs.io/
- The Twelve-Factor App — *Config*. https://12factor.net/config
- msgspec — *Benchmarks*. https://jcristharif.com/msgspec/benchmarks.html
