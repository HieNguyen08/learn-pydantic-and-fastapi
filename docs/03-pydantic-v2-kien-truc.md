# Module 03 — Pydantic v2: kiến trúc và mô hình validation

> Thời lượng: ~50 phút · Mức độ: Trung bình · Tiên quyết: Module 01

Module 01 trả lời câu hỏi *vì sao* cần parse dữ liệu ở ranh giới. Module này trả lời *Pydantic làm điều đó như thế nào*: từ một class Python có type hint, thư viện dựng ra một **cây validator viết bằng Rust**, chạy nó trên byte JSON hoặc object Python, và trả về một object có kiểu hoặc một danh sách lỗi có cấu trúc. Hiểu kiến trúc này giải thích hầu hết các "hiện tượng lạ" bạn sẽ gặp: vì sao `model_validate_json` nhanh gấp đôi `json.loads` + `model_validate`, vì sao trường `int` nhận cả `True`, vì sao định nghĩa class tốn vài mili-giây còn validate chỉ tốn vài micro-giây, và vì sao `x: int | None` vẫn là trường **bắt buộc**.

Mọi hành vi trong module được chạy thật với **Pydantic 2.14.1 / pydantic-core 2.50.1, Python 3.13**.

## Mục tiêu học tập

Sau module này, bạn có thể:

1. Dùng thành thạo API cốt lõi của `BaseModel`: `model_validate`, `model_validate_json`, `model_validate_strings`, `model_construct`, `model_dump`, `model_fields_set`.
2. Mô tả **kiến trúc hai tầng**: Python sinh *core schema* lúc định nghĩa class → pydantic-core (Rust) dựng `SchemaValidator`/`SchemaSerializer`; giải thích vì sao chi phí dồn vào lúc import.
3. Đọc và dự đoán **bảng chuyển đổi lax/strict** cho `int`, `bool`, `str`, `float`, `Decimal`, `datetime` — kể cả các trường hợp bất ngờ (`True` → `1`, `"4_2"` → `42`, `"82.500"` → `Decimal("82.500")`).
4. Phân tích cấu trúc **`ValidationError`** (`type`, `loc`, `msg`, `input`, `ctx`) và biến nó thành phản hồi máy đọc được.
5. Chọn đúng các tùy chọn `ConfigDict` cho model request, response và value object.
6. Phân biệt trường **bắt buộc / có mặc định / cho phép None / vắng mặt** (sentinel `MISSING`), và dùng đúng cho API `PATCH`.
7. Dùng `TypeAdapter` cho kiểu không phải model và tránh anti-pattern dựng lại adapter mỗi request.

---

## 1. API cốt lõi trong 5 phút

```python
from datetime import datetime
from typing import Annotated, Literal
from pydantic import BaseModel, Field

class Line(BaseModel):
    line_no: Annotated[int, Field(ge=1)]
    sku: Annotated[str, Field(min_length=1, max_length=50)]
    quantity: Annotated[float, Field(gt=0)]
    unit_price: Annotated[int, Field(ge=0)]          # VND, số nguyên
    vat_rate: Literal["0", "5", "8", "10", "KCT", "KKKNT"]

class Invoice(BaseModel):
    series: str
    number: Annotated[int, Field(ge=1, le=99_999_999)]
    issued_at: datetime
    lines: Annotated[list[Line], Field(min_length=1, max_length=1000)]

raw = b'''{"series": "1C26TMK", "number": 1024, "issued_at": "2026-10-13T11:45:00+07:00",
          "lines": [{"line_no": 1, "sku": "SKU-1", "quantity": 3, "unit_price": 27500, "vat_rate": "8"}]}'''

inv = Invoice.model_validate_json(raw)     # bytes/str JSON → Invoice (đường nhanh nhất)
inv2 = Invoice.model_validate({...})       # dict/object Python → Invoice
inv.lines[0].quantity                       # 3.0 — đã chuyển int → float
inv.model_dump()                            # Invoice → dict Python
inv.model_dump_json()                       # Invoice → str JSON
```

Bốn cửa vào khác nhau về **nguồn dữ liệu**, không chỉ về cú pháp:

| Phương thức | Đầu vào | Dùng khi |
|---|---|---|
| `model_validate_json(b)` | `str`/`bytes` JSON | body HTTP, message queue, file JSON — **luôn ưu tiên** |
| `model_validate(obj)` | `dict`, object Python | dữ liệu đã ở dạng Python (ORM với `from_attributes`, kết quả thư viện khác) |
| `model_validate_strings(d)` | dict mà mọi lá là chuỗi | dữ liệu dạng text: query string, CSV, biến môi trường |
| `model_construct(**kw)` | giá trị **tin tưởng tuyệt đối** | dữ liệu đọc từ DB của chính mình, đã validate khi ghi — **không kiểm tra gì** |

`model_construct` bỏ qua toàn bộ validation: nhanh, nhưng mọi giả định "đã parse" của Module 01 không còn đúng. Chỉ dùng cho dữ liệu đã đi qua chính model này trước đó (ví dụ cache nội bộ), và đo trước khi quyết định (Module 06).

---

## 2. Kiến trúc hai tầng: Python mô tả, Rust thực thi

### 2.1. Vấn đề

Pydantic v1 viết bằng Python (biên dịch bằng Cython), duyệt type hint **mỗi lần validate**. Mỗi trường là một chuỗi lời gọi hàm Python. Với payload lồng nhau và nhiều phần tử, chi phí đó tăng nhanh. Bài công bố Pydantic v2 (2023) báo cáo bản viết lại nhanh hơn v1 khoảng **4–50 lần** tùy model.

### 2.2. Ý tưởng: biên dịch kiểu thành một cây validator

Pydantic v2 tách thành hai tầng:

1. **Tầng Python (`pydantic`)** chạy **một lần, lúc định nghĩa class**: metaclass thu thập trường (`FieldInfo`), đọc type hint, `Annotated` metadata, validator, cấu hình; rồi `GenerateSchema` sinh một **core schema** — một cây `dict` thuần dữ liệu mô tả *phải kiểm tra gì*.
2. **Tầng Rust (`pydantic-core`, qua PyO3)** nhận core schema và dựng **`SchemaValidator`** (cây object Rust thực thi kiểm tra) và **`SchemaSerializer`**. Mỗi lần validate chỉ chạy cây Rust này; không còn duyệt type hint.

<!-- placeholder-architecture -->

<!-- fig:architecture -->
<figure markdown="span">
  ![Kiến trúc hai tầng: lúc định nghĩa class, Python sinh core schema và pydantic-core dựng cây validator/serializer bằng Rust; mỗi request chỉ chạy cây Rust](assets/figures/03/architecture.light.svg#only-light){ loading=lazy }
  ![Kiến trúc hai tầng: lúc định nghĩa class, Python sinh core schema và pydantic-core dựng cây validator/serializer bằng Rust; mỗi request chỉ chạy cây Rust](assets/figures/03/architecture.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 3.1 — Kiến trúc hai tầng: lúc định nghĩa class, Python sinh core schema và pydantic-core dựng cây validator/serializer bằng Rust; mỗi request chỉ chạy cây Rust.</figcaption>
</figure>
<!-- /fig -->

Core schema của model `Line` rút gọn (in thật bằng `Line.__pydantic_core_schema__`, bỏ metadata):

```python
{'type': 'model',
 'schema': {'type': 'model-fields',
            'model_name': 'Line',
            'computed_fields': [],
            'fields': {'quantity': {'type': 'model-field', 'schema': {'type': 'float', 'gt': 0}},
                       'vat_rate': {'type': 'model-field',
                                    'schema': {'type': 'literal',
                                               'expected': ['0', '5', '8', '10', 'KCT', 'KKKNT']}}}}}
```

Và object Rust được dựng từ nó (`repr(Line.__pydantic_validator__)`, rút gọn):

```text
SchemaValidator(title="Line", validator=Model(
    ModelValidator { revalidate: Never, validator: ModelFields(
        ModelFieldsValidator { fields: [
            Field { name: "quantity", lookup_path: "quantity", validator: ConstrainedFloat { gt: 0 ... } },
            Field { name: "vat_rate", validator: Literal { expected_str: {"0","5","8",...} } } ] } ) } ))
```

Hai chi tiết đáng chú ý:

- `Literal` được biên dịch thành một **tập băm** các chuỗi được phép → kiểm tra $O(1)$, không phải so sánh tuần tự.
- Ràng buộc `gt=0` nằm **trong** validator `float` của Rust — không có lời gọi hàm Python nào. Đây là lý do Module 04 khuyên đẩy ràng buộc xuống `Field(...)`/`annotated_types` thay vì viết validator Python khi có thể.

### 2.3. Cây validator của một hóa đơn

<!-- placeholder-validator-tree -->

<!-- fig:validator-tree -->
<figure markdown="span">
  ![Cây validator của Invoice](assets/figures/03/validator-tree.light.svg#only-light){ loading=lazy }
  ![Cây validator của Invoice](assets/figures/03/validator-tree.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 3.2 — Cây validator của Invoice. Chỉ các nút có validator Python (model_validator, AfterValidator…) mới quay lại trình thông dịch.</figcaption>
</figure>
<!-- /fig -->

Khi bạn gọi `Invoice.model_validate_json(raw)`:

1. **jiter** (bộ parse JSON viết bằng Rust của dự án Pydantic) phân tích byte thành biểu diễn JSON trong bộ nhớ Rust.
2. `ModelValidator(Invoice)` → `ModelFieldsValidator` duyệt các khóa; với mỗi trường, gọi validator con với **đường dẫn vị trí** (`loc`) được nối thêm: `('lines', 5, 'quantity')`.
3. Validator `list` duyệt từng phần tử, gọi `ModelValidator(Line)`; lỗi của từng phần tử được **gom lại**, không dừng ở lỗi đầu tiên (Module 01, mục 7.2).
4. Validator lá (`int`, `float`, `str`, `literal`, `datetime`) kiểm tra kiểu + ràng buộc và tạo object Python cuối cùng.
5. Validator Python của bạn (`@field_validator`, `@model_validator`, `AfterValidator`) được gọi tại đúng nút của cây — đây là chỗ duy nhất quay lại trình thông dịch Python.
6. Nếu có lỗi ở bất kỳ đâu: tạo một `ValidationError` chứa tất cả lỗi; nếu không: trả object model.

### 2.4. Vì sao `model_validate_json` nhanh hơn `json.loads` + `model_validate`

<!-- placeholder-json-path -->

<!-- fig:json-path -->
<figure markdown="span">
  ![Số đo thật, hóa đơn 12 dòng: parse + validate bằng modelvalidatejson tốn ngang chỉ parse bằng json](assets/figures/03/json-path.light.svg#only-light){ loading=lazy }
  ![Số đo thật, hóa đơn 12 dòng: parse + validate bằng modelvalidatejson tốn ngang chỉ parse bằng json](assets/figures/03/json-path.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 3.3 — Số đo thật, hóa đơn 12 dòng: parse + validate bằng model_validate_json tốn ngang chỉ parse bằng json.loads, và nhanh gấp đôi json.loads + model_validate.</figcaption>
</figure>
<!-- /fig -->

Số đo thật trên hóa đơn 12 dòng (thời gian tốt nhất trong 11 lần lặp, script `scripts/bench/bench_validation.py`):

| Cách làm | µs/hóa đơn |
|---|---|
| `json.loads(raw)` (chỉ parse, chưa kiểm tra gì) | ~23 |
| `Invoice.model_validate_json(raw)` (parse **và** validate mọi ràng buộc trường) | ~23 |
| `Invoice.model_validate(json.loads(raw))` | ~47 |

Đường `json.loads` tạo ra **toàn bộ cây object Python trung gian** (dict, list, str, int cho mọi giá trị) chỉ để Pydantic đọc lại rồi vứt đi. Đường JSON trực tiếp bỏ qua bước đó: jiter parse trong Rust, validator đọc từ biểu diễn Rust, và chỉ tạo object Python cho **kết quả cuối**. Hệ quả thực tế: parse **và** validate bằng Pydantic tốn ngang **chỉ parse** bằng `json.loads` của thư viện chuẩn, và nhanh gấp đôi đường `json.loads` + `model_validate`. FastAPI tận dụng điều này khi đọc body (Module 07).

### 2.5. Chi phí dồn vào lúc định nghĩa class

Dựng core schema và cây Rust tốn thời gian **một lần**. Đo thật (script `bench_misc.py`, mục `schema`): định nghĩa một model có $k$ trường `int` ràng buộc tốn khoảng **0,6 ms với 5 trường đến ~14 ms với 200 trường**, trong khi validate một instance của chính model đó chỉ tốn **1,7–24 µs** — chênh nhau gần ba bậc độ lớn. Ba model của hóa đơn (Buyer, Line, Invoice có validator) tốn khoảng **5,6 ms** để định nghĩa.

<!-- placeholder-build-cost -->

<!-- fig:build-cost -->
<figure markdown="span">
  ![Số đo thật: thời gian định nghĩa model theo số trường so với thời gian validate một instance (nhãn ×N là tỷ lệ giữa hai thời gian)](assets/figures/03/build-cost.light.svg#only-light){ loading=lazy }
  ![Số đo thật: thời gian định nghĩa model theo số trường so với thời gian validate một instance (nhãn ×N là tỷ lệ giữa hai thời gian)](assets/figures/03/build-cost.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 3.4 — Số đo thật: thời gian định nghĩa model theo số trường so với thời gian validate một instance (nhãn ×N là tỷ lệ giữa hai thời gian).</figcaption>
</figure>
<!-- /fig -->

Ý nghĩa:

- Một service có 300 model trả ~1–2 giây khởi động chỉ cho Pydantic. Chấp nhận được với server chạy lâu; đáng để ý với CLI, serverless (cold start) và test.
- `model_config = ConfigDict(defer_build=True)` hoãn việc dựng đến lần dùng đầu tiên (đo được: thời gian định nghĩa class còn khoảng 40–50%). Hữu ích khi có nhiều model nhưng mỗi tiến trình chỉ dùng một phần.
- **Không bao giờ** định nghĩa model hay tạo `TypeAdapter` bên trong hàm xử lý request. Mục 7 đo anti-pattern này.

---

## 3. Lax và strict: bảng chuyển đổi thật

### 3.1. Vấn đề

Module 01 đã lập luận về *khi nào* nên lax/strict. Giờ là *chính xác* Pydantic chấp nhận gì. Bảng dưới được sinh bằng cách chạy `TypeAdapter(T).validate_python(v, strict=...)` và `validate_json(...)` trên Pydantic 2.14.1 — không phải chép từ tài liệu.

<!-- placeholder-coercion -->

<!-- fig:coercion -->
<figure markdown="span">
  ![Bảng chuyển đổi được sinh bằng cách chạy TypeAdapter(T)](assets/figures/03/coercion.light.svg#only-light){ loading=lazy }
  ![Bảng chuyển đổi được sinh bằng cách chạy TypeAdapter(T)](assets/figures/03/coercion.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 3.5 — Bảng chuyển đổi được sinh bằng cách chạy TypeAdapter(T).validate_python/validate_json với strict=False/True trên Pydantic 2.14.1.</figcaption>
</figure>
<!-- /fig -->

### 3.2. Đọc bảng: những điều bất ngờ

**`int`, chế độ lax:**

| Đầu vào | Lax | Strict | Ghi chú |
|---|---|---|---|
| `42` | `42` | `42` | |
| `"42"`, `" 42 "`, `"42.0"` | `42` | lỗi `int_type` | khoảng trắng được bỏ; `"42.0"` được chấp nhận vì phần thập phân bằng 0 |
| `"4_2"` | **`42`** | lỗi | cú pháp gạch dưới của literal Python |
| `42.0` | `42` | lỗi | float có phần thập phân 0 |
| `42.5` | lỗi `int_from_float` | lỗi | không làm tròn ngầm |
| `True` (cả JSON `true`) | **`1`** | lỗi | vì `bool` là lớp con của `int` trong Python |
| `"0x2a"`, `"1e3"` | lỗi `int_parsing` | lỗi | không nhận cơ số 16 hay ký pháp khoa học |

Với trường tiền `unit_price: int`, JSON `"unit_price": true` được chấp nhận thành **1 đồng** ở chế độ lax. Đó là một lỗi tích hợp phía client bị che giấu — đúng loại "dễ dãi kiểu Postel" mà RFC 9413 cảnh báo. Strict chặn được.

**`bool`, chế độ lax:** nhận `1/0`, `1.0`, và các chuỗi `"true"`, `"TRUE"`, `"yes"`, `"on"`, `"1"`, `"y"` (và phủ định tương ứng); `2` bị từ chối. Thuận tiện cho query string (`?include_lines=yes`), nguy hiểm cho body.

**`str`:** **không** tự chuyển số thành chuỗi kể cả ở lax (`42` → lỗi `string_type`), trừ khi bật `coerce_numbers_to_str`. Đây là thay đổi lớn so với v1 (v1 nhận `42` thành `"42"`). Mã số thuế gửi dạng số `100233488` (mất số 0 đầu!) bị từ chối — một hành vi **đúng**.

**`datetime`:**

- Lax nhận chuỗi ISO 8601, chuỗi `"2026-10-13"` (thành nửa đêm), số Unix timestamp và chuỗi số timestamp.
- Chuỗi **không múi giờ** `"2026-10-13 11:45"` được nhận thành `datetime` **naive**. Với hóa đơn, thời điểm lập phải có múi giờ: dùng `AwareDatetime` (từ chối naive) thay cho `datetime`.
- Strict ở chế độ Python chỉ nhận object `datetime`; strict ở chế độ JSON vẫn nhận chuỗi ISO (vì JSON không có kiểu ngày giờ) nhưng từ chối `"2026-10-13"` thiếu giờ.

**`Decimal`:** lax và cả strict-JSON nhận chuỗi số và số: `"82.500"` → `Decimal("82.500")` — tức **82,5**, trong khi người Việt viết "82.500" để chỉ tám mươi hai nghìn năm trăm. Nếu API nhận tiền dạng chuỗi, phải ép định dạng bằng `pattern` hoặc dùng `int` VND.

**`float`:** nhận `nan`, `inf` mặc định (`allow_inf_nan=True`). Với số lượng, đặt `allow_inf_nan=False` (trong `Field` hoặc `ConfigDict`), nếu không `quantity = inf` qua được `gt=0`.

### 3.3. Bật strict ở đâu

```python
from pydantic import BaseModel, ConfigDict, Field, Strict
from typing import Annotated

class InvoiceIn(BaseModel):
    model_config = ConfigDict(strict=True)            # cả model
    unit_price: int
    issued_at: AwareDatetime                          # JSON strict vẫn nhận chuỗi ISO có múi giờ

class Query(BaseModel):                               # tham số URL: giữ lax
    page_size: Annotated[int, Field(ge=1, le=200)] = 50
    include_lines: bool = False

class Mixed(BaseModel):
    amount: Annotated[int, Strict()]                  # chỉ một trường
    note: str = ""

Invoice.model_validate_json(raw, strict=True)         # theo lời gọi
```

Khuyến nghị cho `invoice-api`: **model body có `strict=True`**; model tham số query/path/header để lax (FastAPI cần lax để biến chuỗi URL thành số).

---

## 4. Cấu trúc lỗi: `ValidationError`

### 4.1. Một lỗi gồm những gì

```python
from pydantic import ValidationError

bad = {"series": "1C26TMK", "number": 0, "issued_at": "13/10/2026",
       "lines": [{"line_no": 1, "sku": "", "quantity": -2, "unit_price": "abc", "vat_rate": "7"}]}
try:
    Invoice.model_validate(bad)
except ValidationError as e:
    print(e.error_count())
    for err in e.errors(include_url=False):
        print(err["loc"], err["type"], err.get("ctx"))
```

```text
6
('number',) greater_than_equal {'ge': 1}
('issued_at',) datetime_from_date_parsing {'error': 'invalid character in year'}
('lines', 0, 'sku') string_too_short {'min_length': 1}
('lines', 0, 'quantity') greater_than {'gt': 0.0}
('lines', 0, 'unit_price') int_parsing None
('lines', 0, 'vat_rate') literal_error {'expected': "'0', '5', '8', '10', 'KCT' or 'KKKNT'"}
```

Mỗi lỗi có:

- **`type`**: mã lỗi ổn định, máy đọc được (`greater_than`, `int_parsing`, `literal_error`…). Dùng nó để dịch thông báo hoặc phân loại — **đừng** so khớp chuỗi `msg`.
- **`loc`**: đường dẫn từ gốc đến giá trị lỗi, gồm tên trường và chỉ số danh sách. Client POS dùng nó để tô đỏ đúng ô dòng hàng thứ 1.
- **`msg`**: thông báo tiếng Anh cho người.
- **`input`**: giá trị đầu vào gây lỗi — **cẩn thận**: có thể chứa dữ liệu nhạy cảm (mật khẩu, số thẻ). Không log nguyên văn ở môi trường production; FastAPI mặc định trả `input` trong response 422 (Module 07, 11).
- **`ctx`**: tham số của ràng buộc (`{'ge': 1}`) — để dựng thông báo bản địa hóa.
- **`url`**: link tài liệu cho mã lỗi.

<!-- placeholder-error-anatomy -->

<!-- fig:error-anatomy -->
<figure markdown="span">
  ![Một phần tử của ValidationError](assets/figures/03/error-anatomy.light.svg#only-light){ loading=lazy }
  ![Một phần tử của ValidationError](assets/figures/03/error-anatomy.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 3.6 — Một phần tử của ValidationError.errors() và cách ánh xạ sang mục lỗi trong Problem Details.</figcaption>
</figure>
<!-- /fig -->

### 4.2. Thông báo tiếng Việt từ `type` và `ctx`

```python
VI = {
    "missing": "Thiếu trường bắt buộc",
    "greater_than": "Phải lớn hơn {gt}",
    "greater_than_equal": "Phải lớn hơn hoặc bằng {ge}",
    "string_too_short": "Cần ít nhất {min_length} ký tự",
    "int_parsing": "Phải là số nguyên",
    "literal_error": "Chỉ nhận một trong: {expected}",
    "extra_forbidden": "Trường không được phép",
}

def to_problem_errors(e: ValidationError) -> list[dict]:
    out = []
    for err in e.errors(include_url=False, include_input=False):   # không trả lại input
        tpl = VI.get(err["type"], err["msg"])
        out.append({"field": ".".join(map(str, err["loc"])), "code": err["type"],
                    "message": tpl.format(**(err.get("ctx") or {}))})
    return out
```

Module 07 gắn hàm này vào exception handler của FastAPI để trả về Problem Details (RFC 9457).

---

## 5. Cấu hình model: `ConfigDict`

### 5.1. Các tùy chọn quan trọng

| Tùy chọn | Mặc định | Tác dụng | Khuyến nghị cho `invoice-api` |
|---|---|---|---|
| `extra` | `"ignore"` | trường lạ: `ignore` (bỏ qua), `forbid` (lỗi), `allow` (giữ lại) | **`forbid`** cho model request: client gõ sai tên trường (`unitprice`) bị báo ngay thay vì âm thầm thành giá trị mặc định |
| `strict` | `False` | strict cho mọi trường | `True` cho body tài chính |
| `frozen` | `False` | instance bất biến, có `__hash__` | `True` cho value object (`Money`, `TaxCode`) |
| `validate_assignment` | `False` | validate lại khi gán thuộc tính | `True` cho model domain bị sửa sau khi tạo; tốn thêm chi phí mỗi lần gán |
| `str_strip_whitespace` | `False` | bỏ khoảng trắng đầu/cuối chuỗi | `True` cho tên, địa chỉ do người nhập |
| `allow_inf_nan` | `True` | float nhận `inf`/`nan` | `False` |
| `from_attributes` | `False` | đọc từ thuộc tính object (ORM) | `True` cho model response tạo từ row SQLAlchemy (Module 10) |
| `populate_by_name` / `validate_by_name` | `False` | nhận cả tên trường lẫn alias | xem Module 05 |
| `revalidate_instances` | `"never"` | validate lại instance model được truyền vào | `"never"` (mặc định) là đủ khi model đã frozen |
| `defer_build` | `False` | hoãn dựng validator | `True` khi có nhiều model ít dùng |
| `use_attribute_docstrings` | `False` | lấy docstring của trường làm `description` cho OpenAPI | `True` — tài liệu API viết một lần |

Kiểm chứng `extra`:

```python
class StrictIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    unit_price: int

StrictIn.model_validate({"unit_price": 1, "unitprice": 2})
# ValidationError: ('unitprice',) extra_forbidden — Extra inputs are not permitted

class Lenient(BaseModel):
    unit_price: int

Lenient.model_validate({"unit_price": 1, "is_admin": True})   # unit_price=1 — is_admin âm thầm biến mất
```

`extra="ignore"` (mặc định) **an toàn** về bảo mật — trường lạ không bao giờ lọt vào model — nhưng che lỗi tích hợp. `extra="allow"` thì nguy hiểm khi model được đổ thẳng vào ORM (mass assignment, Module 11).

<!-- placeholder-extra -->

<!-- fig:extra -->
<figure markdown="span">
  ![Ba chế độ extra với cùng một đầu vào có trường gõ sai tên](assets/figures/03/extra.light.svg#only-light){ loading=lazy }
  ![Ba chế độ extra với cùng một đầu vào có trường gõ sai tên](assets/figures/03/extra.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 3.7 — Ba chế độ extra với cùng một đầu vào có trường gõ sai tên.</figcaption>
</figure>
<!-- /fig -->

---

## 6. Trường bắt buộc, mặc định, `None` và `MISSING`

### 6.1. Bốn khai báo dễ nhầm

| Khai báo | Bắt buộc? | Nhận `null`? |
|---|---|---|
| `x: int` | có | không |
| `x: int = 0` | không (mặc định 0) | không |
| `x: int \| None` | **có** | có |
| `x: int \| None = None` | không | có |

Hàng thứ ba là cạm bẫy kinh điển khi chuyển từ v1: ở v1, `Optional[int]` ngầm có mặc định `None`; ở v2, **kiểu** (có cho phép `None` không) và **tính bắt buộc** (có mặc định không) là hai chuyện độc lập. Kiểm chứng: `class M(BaseModel): a: int | None` → `M()` báo lỗi `missing`.

<!-- placeholder-required -->

<!-- fig:required -->
<figure markdown="span">
  ![Kiểu và tính bắt buộc là hai chiều độc lập trong Pydantic v2](assets/figures/03/required.light.svg#only-light){ loading=lazy }
  ![Kiểu và tính bắt buộc là hai chiều độc lập trong Pydantic v2](assets/figures/03/required.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 3.8 — Kiểu và tính bắt buộc là hai chiều độc lập trong Pydantic v2.</figcaption>
</figure>
<!-- /fig -->

Mặc định mutable an toàn: `tags: list[str] = []` — Pydantic sao chép mặc định cho mỗi instance (đã thử: thêm phần tử vào `d1.tags` không ảnh hưởng `d2.tags`), khác với tham số mặc định của hàm Python. Với giá trị cần tính lúc tạo (thời điểm, UUID), dùng `Field(default_factory=...)`.

### 6.2. API `PATCH`: phân biệt "không gửi" và "gửi null"

Với `PATCH /v1/drafts/{id}`, ba trạng thái của một trường có nghĩa khác nhau: **không gửi** (giữ nguyên), **gửi `null`** (xóa giá trị), **gửi giá trị** (cập nhật). Hai cách trong Pydantic 2.14:

```python
from pydantic import BaseModel, MISSING

class DraftPatch(BaseModel):
    buyer_email: str | None | MISSING = MISSING     # sentinel MISSING: ổn định từ 2.14
    note: str | None | MISSING = MISSING

p = DraftPatch.model_validate({"buyer_email": None})
print(p)                     # buyer_email=None note=MISSING
print(p.model_dump())        # {'buyer_email': None}  — trường MISSING không xuất hiện khi dump
print(p.model_fields_set)    # {'buyer_email'}
```

Cách cũ hơn vẫn dùng được: mặc định `None` + đọc `model_fields_set` (hoặc `model_dump(exclude_unset=True)`) để biết trường nào client thực sự gửi. `MISSING` tốt hơn vì trạng thái "vắng mặt" nằm **trong kiểu** — đúng tinh thần Module 01.

---

## 7. `TypeAdapter`: validate mọi kiểu, không chỉ model

### 7.1. Khi nào cần

`BaseModel` mô tả object có trường. Nhưng đôi khi đầu vào là một **danh sách** hóa đơn, một `dict[str, int]`, một `TypedDict` từ thư viện khác, hay một kiểu tinh chỉnh như `MST` (Module 01). `TypeAdapter(T)` dựng cùng cỗ máy validator/serializer cho kiểu bất kỳ:

```python
from pydantic import TypeAdapter

InvoiceList = TypeAdapter(list[Invoice])           # tạo MỘT LẦN ở cấp module
invoices = InvoiceList.validate_json(batch_bytes)  # body của POST /v1/invoice-batches
schema = InvoiceList.json_schema()                 # JSON Schema cho tài liệu
```

### 7.2. Anti-pattern: dựng adapter trong request

Đo thật trên hóa đơn 12 dòng: validate qua adapter **tạo sẵn** tốn khoảng **23 µs**; tạo `TypeAdapter(list[Invoice])` **mới mỗi request** rồi validate tốn khoảng **89 µs** (mức `schema`) đến **135 µs** (mức `full`) — gấp 4–5 lần, toàn bộ phần chênh là chi phí dựng schema bị lặp lại. Riêng việc dựng `TypeAdapter(list[Invoice])` đo được ~78 µs. Quy tắc: adapter là **hằng số cấp module**, như một regex đã biên dịch.

<!-- placeholder-typeadapter -->

<!-- fig:typeadapter -->
<figure markdown="span">
  ![Số đo thật: dựng TypeAdapter(listInvoice) trong mỗi request làm chi phí tăng nhiều lần so với adapter tạo sẵn](assets/figures/03/typeadapter.light.svg#only-light){ loading=lazy }
  ![Số đo thật: dựng TypeAdapter(listInvoice) trong mỗi request làm chi phí tăng nhiều lần so với adapter tạo sẵn](assets/figures/03/typeadapter.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 3.9 — Số đo thật: dựng TypeAdapter(list[Invoice]) trong mỗi request làm chi phí tăng nhiều lần so với adapter tạo sẵn.</figcaption>
</figure>
<!-- /fig -->

### 7.3. `BaseModel`, `dataclass`, `TypedDict`: chọn gì

| Cấu trúc | Validate khi | Ưu điểm | Dùng cho |
|---|---|---|---|
| `BaseModel` | tạo instance | đủ tính năng: config, serializer, JSON Schema, `model_*` API | request/response API, mọi dữ liệu ở ranh giới |
| `pydantic.dataclasses.dataclass` | tạo instance | giữ ngữ nghĩa dataclass chuẩn (so sánh, `asdict`), thêm validation | code đã dùng dataclass, muốn thêm kiểm tra |
| `TypedDict` + `TypeAdapter` | gọi adapter | kết quả vẫn là `dict` thường — không bọc object | dữ liệu đi tiếp vào thư viện chỉ nhận `dict`; tối ưu khi không cần object |
| `dataclass` chuẩn | không bao giờ | không phụ thuộc thư viện | lõi domain thuần, **sau** ranh giới |

Một kiến trúc sạch cho `invoice-api`: `BaseModel` ở ranh giới HTTP (parse/serialize), domain có thể là `BaseModel` frozen hoặc dataclass thuần; ORM model (SQLAlchemy) riêng; chuyển đổi tường minh giữa các lớp (Module 10).

---

## 8. Case Mekong Cloud: model hóa đơn phiên bản 1

```python
from datetime import datetime
from typing import Annotated, Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

VND = Annotated[int, Field(ge=0, le=10**15)]                      # tiền: số nguyên VND, có trần
Qty = Annotated[float, Field(gt=0, le=10**9, allow_inf_nan=False)]
TaxCode = Annotated[str, Field(pattern=r"^\d{10}(\d{3})?$")]      # checksum ở Module 04
VatRate = Literal["0", "5", "8", "10", "KCT", "KKKNT"]

class RequestModel(BaseModel):
    """Cấu hình chung cho mọi model nhận từ client."""
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True,
                              use_attribute_docstrings=True)

class BuyerIn(RequestModel):
    name: Annotated[str, Field(min_length=1, max_length=400)]
    tax_code: TaxCode | None = None
    email: Annotated[str, Field(max_length=254)] | None = None
    address: Annotated[str, Field(max_length=400)] = ""

class LineIn(RequestModel):
    line_no: Annotated[int, Field(ge=1, le=1000)]
    sku: Annotated[str, Field(min_length=1, max_length=50)]
    name: Annotated[str, Field(min_length=1, max_length=500)]
    unit: Annotated[str, Field(min_length=1, max_length=20)]
    quantity: Qty
    unit_price: VND
    vat_rate: VatRate
    amount: VND

class InvoiceIn(RequestModel):
    series: Annotated[str, Field(pattern=r"^[0-9][A-Z0-9]{1,9}$")]
    number: Annotated[int, Field(ge=1, le=99_999_999)]
    seller_tax_code: TaxCode
    buyer: BuyerIn
    issued_at: AwareDatetime
    """Thời điểm lập hóa đơn, bắt buộc có múi giờ."""
    currency: Literal["VND"] = "VND"
    lines: Annotated[list[LineIn], Field(min_length=1, max_length=1000)]
    total_before_tax: VND
    total_tax: VND
    total: VND
```

Phiên bản này đã phủ tầng 1 và tầng 2 của Module 01 (cú pháp, cấu trúc, ràng buộc từng trường) **hoàn toàn trong Rust**. Còn thiếu tầng 3 — checksum MST, `amount = round(qty × price)`, tổng khớp — chính là nội dung Module 04.

<!-- placeholder-invoice-v1 -->

<!-- fig:invoice-v1 -->
<figure markdown="span">
  ![Phạm vi của InvoiceIn phiên bản 1 trên năm tầng quy tắc của Module 01](assets/figures/03/invoice-v1.light.svg#only-light){ loading=lazy }
  ![Phạm vi của InvoiceIn phiên bản 1 trên năm tầng quy tắc của Module 01](assets/figures/03/invoice-v1.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 3.10 — Phạm vi của InvoiceIn phiên bản 1 trên năm tầng quy tắc của Module 01.</figcaption>
</figure>
<!-- /fig -->

---

## Lỗi thường gặp & cách xử lý

| Triệu chứng | Nguyên nhân gốc | Cách xử lý |
|---|---|---|
| `x: Optional[int]` không còn tự có mặc định sau khi lên v2 | v2 tách kiểu và tính bắt buộc | Thêm `= None` nếu muốn tùy chọn |
| Trường tiền nhận `true` thành 1 | Lax: `bool` là `int` | `strict=True` cho body, hoặc `StrictInt` |
| `"82.500"` thành 82,5 | `Decimal` lax/strict-JSON nhận chuỗi số kiểu Anh | Tiền là `int` VND; nếu nhận chuỗi thì ràng buộc `pattern` |
| Thời điểm lập hóa đơn mất múi giờ | `datetime` nhận chuỗi naive | `AwareDatetime` |
| Client gõ sai tên trường mà không ai biết | `extra="ignore"` mặc định | `extra="forbid"` cho model request |
| Endpoint chậm gấp 4–5 lần không rõ lý do | Tạo `TypeAdapter`/định nghĩa model trong hàm | Đưa lên cấp module |
| Service khởi động chậm, test chậm | Hàng trăm model dựng validator lúc import | `defer_build=True`; chỉ import model cần thiết |
| Log lộ mật khẩu/số thẻ | Log `e.errors()` gồm `input` | `include_input=False`; che dữ liệu nhạy cảm |
| `quantity = inf` lọt qua `gt=0` | `allow_inf_nan=True` mặc định | `allow_inf_nan=False` |

## Tóm tắt (cheat-sheet)

- Cửa vào: `model_validate_json` (ưu tiên) · `model_validate` · `model_validate_strings` · `model_construct` (không kiểm tra).
- Kiến trúc: định nghĩa class → core schema (dict) → `SchemaValidator`/`SchemaSerializer` (Rust). Dựng: ms, một lần; validate: µs, mỗi lần.
- JSON trực tiếp (jiter) tránh tạo cây object trung gian: ~23 µs so với ~47 µs cho `json.loads` + `model_validate` (hóa đơn 12 dòng).
- Lax bất ngờ: `True`→`1`, `"4_2"`→`42`, `"42.0"`→`42`, chuỗi naive → `datetime` naive, `"82.500"` → `Decimal("82.500")`. Số **không** tự thành chuỗi.
- `ValidationError`: dùng `type` + `ctx` + `loc`, đừng so `msg`; cẩn thận `input`.
- Config cho request: `extra="forbid"`, `strict=True`, `str_strip_whitespace=True`, `allow_inf_nan=False`.
- `int | None` vẫn bắt buộc; `MISSING` cho PATCH; mặc định mutable được sao chép.
- `TypeAdapter` là hằng số cấp module; dựng lại mỗi request chậm 4–5 lần.

## Câu hỏi tự kiểm tra / phỏng vấn

1. Điều gì xảy ra lúc định nghĩa một class `BaseModel`, và điều gì xảy ra lúc gọi `model_validate_json`?

    <details markdown="1"><summary>Gợi ý</summary>
    Định nghĩa: metaclass thu thập trường và metadata, sinh core schema (dict), pydantic-core dựng `SchemaValidator`/`SchemaSerializer` bằng Rust. Validate: jiter parse byte, cây validator Rust chạy, gọi validator Python tại các nút có đăng ký, trả object hoặc `ValidationError` gom mọi lỗi.
    </details>

2. Vì sao `model_validate_json(raw)` (parse + validate) tốn ngang `json.loads(raw)` (chỉ parse)?

    <details markdown="1"><summary>Gợi ý</summary>
    `json.loads` phải tạo object Python cho mọi giá trị. Pydantic parse trong Rust và chỉ tạo object Python cho kết quả đã validate (với chuỗi, số nhỏ có thể tái dùng/cache), bỏ qua cây trung gian.
    </details>

3. Với trường `unit_price: int`, liệt kê ba đầu vào JSON mà lax chấp nhận nhưng strict từ chối. Cái nào nguy hiểm nhất với hóa đơn?

    <details markdown="1"><summary>Gợi ý</summary>
    `"27500"`, `27500.0`, `true`. Nguy hiểm nhất là `true` → 1 đồng: che lỗi client nghiêm trọng mà vẫn ra số hợp lệ.
    </details>

4. `class A(BaseModel): x: int | None` — `A()` có hợp lệ không? `A(x=None)`?

    <details markdown="1"><summary>Gợi ý</summary>
    `A()` lỗi `missing` (không có mặc định). `A(x=None)` hợp lệ.
    </details>

5. Thiết kế model cho `PATCH` sao cho phân biệt được "không gửi" và "gửi null".

    <details markdown="1"><summary>Gợi ý</summary>
    Kiểu `T | None | MISSING = MISSING`; trường MISSING không xuất hiện khi dump. Hoặc mặc định `None` + `model_fields_set`/`exclude_unset=True`.
    </details>

6. Tại sao không nên log nguyên `e.errors()` ở production?

    <details markdown="1"><summary>Gợi ý</summary>
    Mỗi lỗi chứa `input` — có thể là mật khẩu, token, số thẻ, PII. Dùng `include_input=False` hoặc che dữ liệu.
    </details>

7. `extra="ignore"` có an toàn không? Khi nào chọn `forbid`, khi nào `allow`?

    <details markdown="1"><summary>Gợi ý</summary>
    An toàn về bảo mật (trường lạ bị bỏ), nhưng che lỗi tích hợp. `forbid` cho request từ client để phát hiện gõ sai; `allow` chỉ khi thực sự cần giữ trường mở rộng và **không** đổ thẳng vào ORM.
    </details>

8. Một đồng nghiệp viết `TypeAdapter(list[Invoice]).validate_json(body)` trong handler. Ước lượng chi phí thêm với 500 req/s.

    <details markdown="1"><summary>Gợi ý</summary>
    Mỗi lần dựng ~70–130 µs thừa → 500 × ~0,1 ms ≈ 50 ms CPU mỗi giây ≈ 5% một core chỉ để dựng lại thứ không đổi. Đưa adapter lên cấp module.
    </details>

9. Khi nào dùng `model_construct`? Rủi ro?

    <details markdown="1"><summary>Gợi ý</summary>
    Khi dữ liệu chắc chắn đã hợp lệ (đã qua chính model đó, đọc lại từ nguồn tin cậy) và đo được validation là nút thắt. Rủi ro: mọi bất biến có thể bị phá, lỗi xuất hiện xa nơi gây ra.
    </details>

10. Vì sao đẩy ràng buộc vào `Field(gt=0)` tốt hơn viết `@field_validator` kiểm tra `> 0`?

    <details markdown="1"><summary>Gợi ý</summary>
    Ràng buộc nằm trong validator Rust, không gọi lại Python; tự sinh JSON Schema (`exclusiveMinimum`); mã lỗi chuẩn (`greater_than`, có `ctx`). Validator Python chậm hơn và JSON Schema không biết về nó.
    </details>

## Bài tập thực hành

1. **Tự sinh bảng chuyển đổi (CPU, 15 phút).** Viết script duyệt danh sách đầu vào × kiểu (`int`, `bool`, `Decimal`, `datetime`, `date`, `UUID`) × (lax/strict) × (python/json) và in bảng như mục 3. Tìm ít nhất hai hành vi khác với dự đoán của bạn.
2. **Đọc core schema (CPU, 10 phút).** In `InvoiceIn.__pydantic_core_schema__` (mục 8) và vẽ lại cây validator bằng tay. Đếm có bao nhiêu nút gọi lại Python.
3. **Lỗi thân thiện (CPU, 20 phút).** Hoàn thiện `to_problem_errors` cho 15 mã lỗi phổ biến, có `loc` dạng `lines[0].quantity`; viết test với payload sai 6 chỗ.
4. **Đo chi phí dựng (CPU, 15 phút).** Dùng `time.perf_counter` đo định nghĩa model 10/50/200 trường có và không có `defer_build`; so với số trong bài.

## Tài liệu tham khảo

Tài liệu chính thức (tra cứu 10/2026, Pydantic 2.14):

- Pydantic — *Architecture*. https://docs.pydantic.dev/latest/internals/architecture/
- Pydantic — *Conversion Table* (bảng chuyển đổi lax/strict chính thức). https://docs.pydantic.dev/latest/concepts/conversion_table/
- Pydantic — *Strict Mode*. https://docs.pydantic.dev/latest/concepts/strict_mode/
- Pydantic — *Models*, *Fields*, *Configuration*, *Type Adapter*. https://docs.pydantic.dev/latest/concepts/models/
- Pydantic — *Validation Errors* (danh sách mã lỗi). https://docs.pydantic.dev/latest/errors/validation_errors/
- Pydantic — *Migration Guide* (v1 → v2). https://docs.pydantic.dev/latest/migration/
- Pydantic — *Pydantic V2 Plan* (2022–2023, kiến trúc và các con số 4–50×). https://docs.pydantic.dev/2.0/blog/pydantic-v2/
- Pydantic — *Pydantic v2.14 release* (MISSING ổn định, TypeForm, Python 3.15). https://pydantic.dev/articles/pydantic-v2-14-release
- pydantic-core (Rust, PyO3). https://github.com/pydantic/pydantic-core
- jiter — bộ parse JSON của Pydantic. https://github.com/pydantic/jiter
- PyO3 — Rust bindings cho Python. https://pyo3.rs/

Tiêu chuẩn:

- ISO 8601 / RFC 3339 — định dạng ngày giờ trên Internet. https://www.rfc-editor.org/rfc/rfc3339
