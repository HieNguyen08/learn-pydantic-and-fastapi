# Module 04 — Validator, kiểu tùy biến & union

> Thời lượng: ~50 phút · Mức độ: Trung bình–Nâng cao · Tiên quyết: Module 01, Module 03

Module 03 dừng ở tầng 2 (cấu trúc và ràng buộc từng trường), toàn bộ chạy trong Rust. Nhưng một hóa đơn còn những quy tắc mà kiểu dữ liệu chuẩn không diễn tả được: mã số thuế phải đúng **chữ số kiểm tra**, `amount` phải bằng **số lượng × đơn giá làm tròn**, ba con số tổng phải **khớp nhau**, một khoản thanh toán có thể là **thẻ, chuyển khoản hay ví điện tử** với các trường khác nhau. Module này dạy bốn công cụ để đưa các quy tắc đó vào kiểu — validator, kiểu tùy biến, union có phân biệt, model generic — và **đo chi phí** của từng công cụ để biết khi nào nên dùng.

Mọi hành vi và số đo được chạy thật với Pydantic 2.14.1 (script `scripts/bench/bench_validators.py`).

## Mục tiêu học tập

Sau module này, bạn có thể:

1. Phân biệt bốn chế độ validator **before / after / wrap / plain**, dùng ở dạng decorator và dạng `Annotated`, và **dự đoán thứ tự chạy** khi xếp chồng nhiều validator.
2. Dùng `ValidationInfo` (`data`, `context`) đúng cách, và giải thích vì sao model validator `after` không chạy khi có lỗi trường.
3. Định lượng chi phí: ràng buộc trong Rust gần như **miễn phí**, validator Python tốn thêm **~30–170 ns** mỗi lần gọi; chọn đúng chỗ đặt quy tắc.
4. Viết **kiểu tùy biến** có thể dùng lại (`Annotated` và `__get_pydantic_core_schema__`), kèm mã lỗi riêng và JSON Schema đúng.
5. Viết **kiểm tra liên trường** cho hóa đơn với `Decimal` và làm tròn half-up, chỉ ra hai bẫy làm tròn (banker's rounding, sai số float).
6. Giải thích thuật toán **smart union**, đo chi phí $O(k)$ và "bùng nổ lỗi" của nó; dùng **discriminated union** ($O(1)$, một lỗi gọn).
7. Dùng **generic model**, `RootModel` và model **đệ quy**, và biết giới hạn độ sâu lồng nhau.

---

## 1. Bốn chế độ validator

### 1.1. Vấn đề

Validator là hàm Python bạn chèn vào cây validator của Module 03. Câu hỏi đầu tiên là nó chạy **trước** hay **sau** validator gốc của kiểu, và nó nhận **giá trị thô** hay **giá trị đã chuyển đổi**.

### 1.2. Định nghĩa

| Chế độ | Chạy khi nào | Nhận | Dùng cho |
|---|---|---|---|
| **after** | sau validator gốc | giá trị **đã** đúng kiểu | quy tắc ngữ nghĩa (checksum, khoảng hợp lệ phức tạp) — phổ biến nhất |
| **before** | trước validator gốc | giá trị **thô** (bất kỳ kiểu gì) | chuẩn hóa đầu vào (bỏ dấu `-` trong MST, đổi `"8%"` → `"8"`) |
| **wrap** | bao quanh validator gốc | giá trị thô + `handler` để gọi validator gốc | thử–bắt lỗi, mặc định khi lỗi, đo đếm, xử lý trước *và* sau |
| **plain** | **thay thế** validator gốc | giá trị thô | khi kiểu gốc không phù hợp; bạn tự chịu trách nhiệm toàn bộ |

Hai cách viết tương đương:

```python
from typing import Annotated
from pydantic import AfterValidator, BaseModel, BeforeValidator, field_validator

def strip_dashes(v):            # before: nhận giá trị thô
    return v.replace("-", "") if isinstance(v, str) else v

def check_len(v: str) -> str:   # after: nhận str đã hợp lệ
    if len(v) not in (10, 13):
        raise ValueError("MST phải có 10 hoặc 13 chữ số")
    return v

# Cách 1 — Annotated: gắn với KIỂU, dùng lại được ở mọi model
TaxCodeStr = Annotated[str, BeforeValidator(strip_dashes), AfterValidator(check_len)]

class Seller(BaseModel):
    tax_code: TaxCodeStr

# Cách 2 — decorator: gắn với TRƯỜNG của một model
class Seller2(BaseModel):
    tax_code: str

    @field_validator("tax_code", mode="before")
    @classmethod
    def _strip(cls, v):
        return strip_dashes(v)

    @field_validator("tax_code")          # mặc định mode="after"
    @classmethod
    def _len(cls, v: str) -> str:
        return check_len(v)
```

Mình khuyên **Annotated cho quy tắc thuộc về kiểu** (MST hợp lệ ở mọi nơi nó xuất hiện) và **decorator cho quy tắc thuộc về model** (một trường chỉ có ý nghĩa trong ngữ cảnh model đó).

### 1.3. Thứ tự chạy: mô hình củ hành

Khi xếp nhiều validator trong một `Annotated`, mỗi validator **bọc** lấy mọi thứ bên trái nó. Thí nghiệm thật:

```python
T = Annotated[int, BeforeValidator(B1), AfterValidator(A1), WrapValidator(W1),
                   BeforeValidator(B2), AfterValidator(A2)]
TypeAdapter(T).validate_python("5")
# thứ tự ghi nhận: B2 → W1:trước → B1 → (int gốc) → A1 → W1:sau → A2
```

Đọc từ trong ra ngoài: lõi là `int`; `B1` và `A1` là lớp sát lõi; `W1` bọc chúng; `B2` và `A2` là lớp ngoài cùng. Một giá trị đi vào sẽ xuyên qua các lớp *before* từ **ngoài vào trong** (phải sang trái), chạm lõi, rồi đi ra qua các lớp *after* từ **trong ra ngoài** (trái sang phải). Validator `wrap` là một lớp có cả hai phía.

<!-- placeholder-onion -->

<!-- fig:onion -->
<figure markdown="span">
  ![Mô hình củ hành của Annotated và thứ tự chạy ghi nhận được khi chạy thật](assets/figures/04/onion.light.svg#only-light){ loading=lazy }
  ![Mô hình củ hành của Annotated và thứ tự chạy ghi nhận được khi chạy thật](assets/figures/04/onion.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 4.1 — Mô hình củ hành của Annotated và thứ tự chạy ghi nhận được khi chạy thật.</figcaption>
</figure>
<!-- /fig -->

Hệ quả thiết kế: đặt **chuẩn hóa** (before) ở ngoài cùng bên phải nếu muốn nó chạy đầu tiên; đặt **kiểm tra rẻ** gần lõi và **kiểm tra đắt** ở ngoài để lỗi rẻ dừng sớm.

### 1.4. Model validator và `ValidationInfo`

```python
from pydantic import BaseModel, ValidationInfo, field_validator, model_validator

class M(BaseModel):
    a: int
    b: int

    @field_validator("b")
    @classmethod
    def chk(cls, v, info: ValidationInfo):
        print(info.data, info.context)       # các trường ĐÃ validate thành công trước b
        return v

    @model_validator(mode="before")
    @classmethod
    def before(cls, data):                   # nhận đầu vào thô: dict, object, bytes…
        return data

    @model_validator(mode="after")
    def after(self):                         # nhận instance đã đầy đủ
        return self

M.model_validate({"a": "1", "b": 2}, context={"tenant_id": 7})
# {'a': 1} {'tenant_id': 7}
M.model_validate({"a": "x", "b": 2})
# info.data == {}  (a lỗi nên không có trong data); model "after" KHÔNG chạy; 1 lỗi
```

Ba điều cần nhớ, đều đã kiểm chứng:

1. `info.data` chỉ chứa **các trường đứng trước** và **đã validate thành công**. Thứ tự khai báo trường quan trọng; đừng giả định trường kia luôn có mặt.
2. Model validator `after` **không chạy** nếu có bất kỳ lỗi trường nào — nó cần mọi trường hợp lệ. Hệ quả: client nhận lỗi trường trước, sửa xong mới thấy lỗi tổng tiền. Đây là cách duy nhất hợp lý (không thể kiểm tra tổng khi một `amount` không phải số), nhưng cần biết để giải thích cho đội tích hợp.
3. `context` là kênh truyền thông tin ngoài dữ liệu vào validator (tenant, ngôn ngữ, thời điểm hiện tại cho quy tắc "không lập hóa đơn ngày tương lai"). Nó **không** là chỗ để truyền session database — tầng 4 thuộc về dependency (Module 01, 08).

---

## 2. Chi phí: ràng buộc trong Rust gần như miễn phí

### 2.1. Thí nghiệm

Validate một danh sách 1.000 số thực dương bằng nhiều cách cài cùng một quy tắc "> 0" (thời gian tốt nhất trong 9 lần lặp, tính trên mỗi phần tử, 1 core):

| Cách cài | ns / phần tử | Thêm so với không kiểm tra |
|---|---|---|
| `float` (không ràng buộc) | 42,3 | — |
| `Annotated[float, Field(gt=0)]` | **42,6** | **+0,3** |
| `AfterValidator(pos)` | 75,2 | +33 |
| `BeforeValidator(pos)` | 85,6 | +43 |
| `PlainValidator(pos_plain)` | 127,6 | +85 |
| `WrapValidator(pos_wrap)` | 214,3 | +172 |
| model `{q}` + `Field(gt=0)` | 366,6 | (chi phí tạo object model) |
| model `{q}` + `@field_validator` | 446,0 | +79 so với dòng trên |

<!-- placeholder-validator-cost -->

<!-- fig:validator-cost -->
<figure markdown="span">
  ![Số đo thật: chi phí mỗi phần tử của sáu cách cài cùng quy tắc «> 0»](assets/figures/04/validator-cost.light.svg#only-light){ loading=lazy }
  ![Số đo thật: chi phí mỗi phần tử của sáu cách cài cùng quy tắc «> 0»](assets/figures/04/validator-cost.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 4.2 — Số đo thật: chi phí mỗi phần tử của sáu cách cài cùng quy tắc «> 0». Ràng buộc trong Rust gần như miễn phí; mỗi validator Python thêm hàng chục đến hàng trăm nano-giây.</figcaption>
</figure>
<!-- /fig -->

### 2.2. Diễn giải

- Ràng buộc `gt` nằm trong validator Rust: một phép so sánh số, không rời Rust. Chi phí đo được nằm trong nhiễu.
- Mỗi validator Python là **một lần quay lại trình thông dịch**: chuyển giá trị Rust → object Python, gọi hàm, nhận kết quả. ~30–40 ns là chi phí tối thiểu; `wrap` đắt nhất vì phải dựng `handler` gọi ngược vào Rust.
- Đặt trong ngữ cảnh: hóa đơn 12 dòng có ~100 giá trị; thêm 10 validator Python mỗi dòng là ~120 × 40 ns ≈ 5 µs — nhỏ so với 25–30 µs validate toàn bộ và vô nghĩa so với một truy vấn database (ms). **Đừng tối ưu sớm**: viết quy tắc ngữ nghĩa bằng Python là đúng.
- Nhưng với quy tắc **có sẵn trong core** (`gt`, `ge`, `max_length`, `pattern`, `multiple_of`, `max_digits`, `Literal`), luôn dùng core: vừa nhanh hơn, vừa **tự sinh JSON Schema** (`exclusiveMinimum`, `pattern`…) mà validator Python không làm được, vừa có mã lỗi chuẩn.

---

## 3. Kiểu tùy biến

### 3.1. Mức 1 — `Annotated` có tên

Cách đơn giản và đủ dùng nhất: đặt tên cho tổ hợp kiểu + ràng buộc + validator.

```python
VND = Annotated[int, Field(ge=0, le=10**15)]                               # tiền: nguyên, có trần
Qty = Annotated[Decimal, Field(gt=0, le=10**9, max_digits=15, decimal_places=4)]
VatRate = Literal["0", "5", "8", "10", "KCT", "KKKNT"]
NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
```

Ưu điểm: không cần class mới, JSON Schema tự sinh, dùng chung ở mọi model. Nhược điểm: giá trị vẫn là `int`/`str` thường — kiểu tĩnh không phân biệt được `VND` với `int` (có thể bổ sung bằng `NewType` cho type checker).

### 3.2. Mức 2 — class có `__get_pydantic_core_schema__`

Khi muốn giá trị mang **kiểu riêng** (để type checker và code nghiệp vụ phân biệt), có **mã lỗi riêng** và **JSON Schema tùy chỉnh**:

```python
from typing import Any
from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic_core import PydanticCustomError, core_schema

WEIGHTS = (31, 29, 23, 19, 17, 13, 7, 5, 3)

class TaxCode(str):
    """Mã số thuế đã chuẩn hóa và kiểm tra chữ số cuối. Chỉ tạo được qua validate."""

    @classmethod
    def _parse(cls, v: str) -> "TaxCode":
        s = v.replace("-", "").replace(".", "").replace(" ", "")
        if len(s) not in (10, 13) or not s.isdigit():
            raise PydanticCustomError("tax_code_format", "MST phải có 10 hoặc 13 chữ số")
        if s[2:9] == "0000000" or (len(s) == 13 and s[10:] == "000"):
            raise PydanticCustomError("tax_code_format", "MST có thành phần không hợp lệ")
        check = 10 - sum(w * int(c) for w, c in zip(WEIGHTS, s)) % 11
        if str(check) != s[9]:
            raise PydanticCustomError("tax_code_checksum", "MST sai chữ số kiểm tra (cần {expected})",
                                      {"expected": check if check < 10 else "không có"})
        return cls(s)

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        # chuỗi 10–17 ký tự (cho phép dấu phân cách) → _parse; khi serialize trả về str thường
        return core_schema.no_info_after_validator_function(
            cls._parse, core_schema.str_schema(min_length=10, max_length=17),
            serialization=core_schema.to_string_ser_schema())

    @classmethod
    def __get_pydantic_json_schema__(cls, cs, handler: GetJsonSchemaHandler):
        js = handler(cs)
        js.update(pattern=r"^\d{10}(-?\d{3})?$", description="Mã số thuế 10 hoặc 13 chữ số",
                  examples=["0100233488"])
        return js
```

Ba điểm của thiết kế:

- **`PydanticCustomError(type, template, ctx)`** thay cho `ValueError`: lỗi có `type` riêng (`tax_code_checksum`) để client và bảng dịch thông báo (Module 03) xử lý theo mã, và `ctx` có giá trị đúng (`expected: 8`).
- **Phần rẻ trong Rust, phần đắt trong Python**: `str_schema(min_length=10, max_length=17)` chặn chuỗi rác trước khi `_parse` chạy.
- **JSON Schema đúng sự thật**: tài liệu OpenAPI cho client thấy `pattern`, ví dụ, mô tả — dù checksum (không biểu diễn được bằng JSON Schema) chỉ kiểm tra ở server.

<!-- placeholder-custom-type -->

<!-- fig:custom-type -->
<figure markdown="span">
  ![Luồng validate của kiểu TaxCode: kiểm tra độ dài trong Rust, chuẩn hóa và checksum trong Python, lỗi có mã riêng, JSON Schema tùy chỉnh](assets/figures/04/custom-type.light.svg#only-light){ loading=lazy }
  ![Luồng validate của kiểu TaxCode: kiểm tra độ dài trong Rust, chuẩn hóa và checksum trong Python, lỗi có mã riêng, JSON Schema tùy chỉnh](assets/figures/04/custom-type.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 4.3 — Luồng validate của kiểu TaxCode: kiểm tra độ dài trong Rust, chuẩn hóa và checksum trong Python, lỗi có mã riêng, JSON Schema tùy chỉnh.</figcaption>
</figure>
<!-- /fig -->

### 3.3. Thư viện có sẵn

Trước khi tự viết, kiểm tra: `annotated-types` (ràng buộc chuẩn `Gt`, `Len`, `MultipleOf`, `Predicate`), các kiểu có sẵn của Pydantic (`EmailStr` cần gói `email-validator`, `AnyUrl`, `IPvAnyAddress`, `SecretStr`, `PastDatetime`, `AwareDatetime`, `UUID4`, `ByteSize`…) và `pydantic-extra-types` (số điện thoại, mã quốc gia, tiền tệ ISO 4217, màu…). Với dữ liệu riêng của Việt Nam (MST, CCCD, mã ngân hàng), bạn tự viết như trên; thuật toán MST có thể đối chiếu với `python-stdnum` (`stdnum.vn.mst`).

---

## 4. Kiểm tra liên trường và bẫy làm tròn

### 4.1. Vấn đề

Ba quy tắc tầng 3 của hóa đơn:

$$
\text{amount}_i = \operatorname{round}(q_i \cdot p_i), \qquad
T_{\text{trước thuế}} = \sum_i \text{amount}_i, \qquad
T_{\text{thuế}} = \sum_i \operatorname{round}\!\left(\text{amount}_i \cdot \frac{r_i}{100}\right), \qquad
T = T_{\text{trước thuế}} + T_{\text{thuế}}.
$$

Câu hỏi kỹ thuật duy nhất là **"round" nghĩa là gì**. Và đó cũng là chỗ hay sai nhất.

### 4.2. Bẫy 1 — `round()` của Python là làm tròn ngân hàng

`round()` trong Python làm tròn **nửa về số chẵn** (banker's rounding): `round(0.5) == 0`, `round(2.5) == 2`. Kế toán thường dùng **nửa lên** (half-up). Ví dụ số với thuế suất 5%:

| amount | amount × 5% | `round()` (half-even) | half-up |
|---|---|---|---|
| 27.510 | 1.375,5 | 1.376 | 1.376 |
| 27.530 | 1.376,5 | **1.376** | **1.377** |

Lệch 1 đồng trên một dòng là đủ để tổng thuế của client và server khác nhau → hóa đơn bị từ chối, hoặc tệ hơn, được chấp nhận với số sai. Quy tắc làm tròn là **quyết định nghiệp vụ** phải ghi trong tài liệu API và cài giống hệt nhau ở mọi bên.

### 4.3. Bẫy 2 — float không biểu diễn được số thập phân

```python
>>> 0.29 * 100
28.999999999999996
>>> int(0.29 * 100)          # cắt phần thập phân
28
```

Số lượng `0,29 kg` × đơn giá `100` đồng thành 28 đồng nếu ai đó dùng `int()`. Với tiền và số lượng có phần thập phân, dùng **`Decimal`** từ đầu (Pydantic parse chuỗi/số JSON thẳng thành `Decimal`, không đi qua float) và làm tròn tường minh:

```python
from decimal import Decimal, ROUND_HALF_UP

def half_up(x: Decimal) -> int:
    return int(x.quantize(Decimal(1), rounding=ROUND_HALF_UP))

half_up(Decimal("1.5") * 18353)        # 27529,5 → 27530
half_up(Decimal(27530) * 5 / 100)      # 1376,5 → 1377
```

<!-- placeholder-rounding -->

<!-- fig:rounding -->
<figure markdown="span">
  ![Mô phỏng 10](assets/figures/04/rounding.light.svg#only-light){ loading=lazy }
  ![Mô phỏng 10](assets/figures/04/rounding.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 4.4 — Mô phỏng 10.000 hóa đơn: độ lệch tổng thuế giữa half-up và round() của Python (trái), và giữa làm tròn từng dòng với làm tròn tổng (phải).</figcaption>
</figure>
<!-- /fig -->

Hai bẫy này không hiếm. Mô phỏng 10.000 hóa đơn 12 dòng (tiền là bội của 10 đồng như thực tế bán lẻ, thuế suất 5/8/10%): **65%** hóa đơn có tổng thuế tính bằng half-up khác tổng tính bằng `round()` của Python (lệch tới 6 đồng), vì với thuế suất 5% mọi `amount` có dạng $20k + 10$ đều cho phần lẻ đúng 0,5.

### 4.4. Bẫy 3 — làm tròn từng dòng hay làm tròn tổng

$\sum_i \operatorname{round}(t_i)$ và $\operatorname{round}(\sum_i t_i)$ có thể lệch nhau. Với $n$ dòng, mỗi lần làm tròn sai lệch tối đa $\tfrac12$, nên

$$
\left|\sum_{i=1}^{n} \operatorname{round}(t_i) - \operatorname{round}\!\Big(\sum_{i=1}^{n} t_i\Big)\right| \le \frac{n}{2} + \frac12.
$$

Hóa đơn 12 dòng có thể lệch tới vài đồng tùy cách tính; trong mô phỏng ở hình trên, **74%** hóa đơn có hai cách tính cho kết quả khác nhau (lệch từ −2 đến +4 đồng). `invoice-api` chọn **làm tròn từng dòng rồi cộng** (khớp với cách in trên hóa đơn: mỗi dòng có tiền thuế riêng) và ghi rõ trong tài liệu.

### 4.5. Cài đặt: model validator `after`

```python
class LineIn(RequestModel):
    ...
    quantity: Qty
    unit_price: VND
    vat_rate: VatRate
    amount: VND

    @model_validator(mode="after")
    def _amount(self):
        expected = half_up(self.quantity * self.unit_price)
        if self.amount != expected:
            raise PydanticCustomError("line_amount",
                                      "amount phải bằng làm tròn(quantity × unit_price) = {expected}",
                                      {"expected": expected})
        return self

    @property
    def tax(self) -> int:
        return half_up(self.amount * RATE[self.vat_rate] / 100)
```

Kiểm tra ở **mức dòng** đặt trong `LineIn` (lỗi có `loc = ('lines', 1)` — client biết dòng nào sai), kiểm tra **tổng** đặt trong `InvoiceIn` (lỗi ở gốc, `loc = ()`). Mã đầy đủ ở mục 7.

---

## 5. Union: smart, left-to-right và discriminated

### 5.1. Vấn đề

Một hóa đơn có thể kèm thông tin thanh toán: thẻ (`last4`), chuyển khoản (`bank_code`, `ref`), tiền mặt, ví điện tử (`provider`, `phone`), voucher (`code`). JSON không mang tên class (Module 01, mục 1.4) — server phải **đoán** object thuộc loại nào.

### 5.2. Smart mode (mặc định)

Với `Card | Transfer | Cash | EWallet | Voucher`, Pydantic thử lần lượt các thành viên: trước hết ở chế độ strict để tìm thành viên khớp **chính xác**; nếu không có, thử lại ở chế độ lax; khi nhiều thành viên cùng hợp lệ, chọn cái "khớp tốt nhất" (với model: nhiều trường được đặt nhất). Hệ quả kiểm chứng được:

```python
TypeAdapter(int | str).validate_python("1")     # '1'  — str khớp chính xác, không ép sang int
TypeAdapter(float | int).validate_python(1)     # 1    — int khớp chính xác, không thành 1.0
```

Hai cái giá:

1. **Chi phí $O(k)$**: trong trường hợp xấu, mọi thành viên đều được thử (có khi hai lượt). Đo thật: chi phí mỗi phần tử tăng gần tuyến tính theo vị trí của thành viên khớp — từ ~570 ns (1 thành viên) lên ~3.500 ns khi thành viên khớp là thành viên thứ 5.
2. **Bùng nổ lỗi**: khi phần tử không khớp thành viên nào, Pydantic báo lỗi của **từng** thành viên. Một khoản thanh toán ví điện tử có `provider: "paypal"` sinh ra **9 lỗi** — client phải tự đoán lỗi nào là lỗi thật.

```python
# một phần tử chuyển khoản thiếu "ref"
smart → 4 lỗi: (0,'Card','method') literal_error, (0,'Card','last4') missing,
               (0,'Transfer','ref') missing, (0,'Cash','method') literal_error
discriminated → 1 lỗi: (0,'transfer','ref') missing
```

### 5.3. Discriminated union (tagged union)

Khi mọi thành viên có một trường **thẻ** (tag) với giá trị `Literal` khác nhau, khai báo nó:

```python
Payment = Annotated[Card | Transfer | Cash | EWallet | Voucher, Field(discriminator="method")]
```

Pydantic dựng một **bảng băm** `method → validator`, đọc tag và nhảy thẳng tới đúng thành viên: $O(1)$, đúng **một** lỗi có `loc` chứa tên tag (`('transfer', 'ref')`), và tag lạ cho lỗi rõ ràng `union_tag_invalid` kèm danh sách tag hợp lệ. JSON Schema sinh ra dùng `oneOf` + `discriminator` của OpenAPI — client sinh code (TypeScript, Kotlin) nhận đúng kiểu.

<!-- fig:union-flow -->
<figure markdown="span">
  ![Smart union thử lần lượt các thành viên; discriminated union tra bảng theo thẻ](assets/figures/04/union-flow.light.svg#only-light){ loading=lazy }
  ![Smart union thử lần lượt các thành viên; discriminated union tra bảng theo thẻ](assets/figures/04/union-flow.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 4.5 — Smart union thử lần lượt các thành viên; discriminated union tra bảng theo thẻ. Khác biệt cũng thể hiện trong OpenAPI.</figcaption>
</figure>
<!-- /fig -->

<!-- placeholder-union-cost -->

<!-- fig:union-cost -->
<figure markdown="span">
  ![Số đo thật: chi phí smart union tăng theo vị trí của thành viên khớp, discriminated union thì không đổi (trái); tốc độ và số lỗi của bốn cách khai báo (phải)](assets/figures/04/union-cost.light.svg#only-light){ loading=lazy }
  ![Số đo thật: chi phí smart union tăng theo vị trí của thành viên khớp, discriminated union thì không đổi (trái); tốc độ và số lỗi của bốn cách khai báo (phải)](assets/figures/04/union-cost.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 4.6 — Số đo thật: chi phí smart union tăng theo vị trí của thành viên khớp, discriminated union thì không đổi (trái); tốc độ và số lỗi của bốn cách khai báo (phải).</figcaption>
</figure>
<!-- /fig -->

| Cách khai báo | ns / phần tử (5 loại, dữ liệu trộn) | Lỗi cho 1 phần tử sai |
|---|---|---|
| smart (mặc định) | ~3.560 | 9 |
| `union_mode="left_to_right"` | ~2.120 | 9 |
| `Field(discriminator="method")` | **~710** | **1** |
| `Discriminator(callable)` | ~990 | 1 |

`left_to_right` thử theo thứ tự khai báo và lấy thành viên hợp lệ đầu tiên — nhanh hơn smart nhưng kết quả phụ thuộc thứ tự, dễ bất ngờ (`int | str` với `"1"` cho ra `1`).

### 5.4. Khi dữ liệu cũ không có tag: `Discriminator(callable)`

API phiên bản cũ của Mekong Cloud gửi thanh toán không có `method`. Một hàm tự suy ra tag từ hình dạng dữ liệu:

```python
from pydantic import Discriminator, Tag

def infer_method(v):
    if isinstance(v, dict):
        if "method" in v: return v["method"]
        if "last4" in v: return "card"
        if "bank_code" in v: return "transfer"
        if "provider" in v: return "ewallet"
        return "cash"
    return getattr(v, "method", None)

PaymentCompat = Annotated[
    Annotated[Card, Tag("card")] | Annotated[Transfer, Tag("transfer")] | Annotated[Cash, Tag("cash")]
    | Annotated[EWallet, Tag("ewallet")] | Annotated[Voucher, Tag("voucher")],
    Discriminator(infer_method),
]
```

Chi phí cao hơn tag thuần một chút (một lời gọi Python), nhưng vẫn $O(1)$ và một lỗi. Nguyên tắc: **thiết kế API mới luôn có tag**; dùng callable để tương thích ngược.

---

## 6. Generic, RootModel và model đệ quy

### 6.1. Generic: một kiểu phân trang cho mọi tài nguyên

```python
from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")

class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None

class InvoiceSummary(BaseModel):
    id: int
    total: int

Page[InvoiceSummary].model_validate({"items": [{"id": 1, "total": "5"}]})
# items=[InvoiceSummary(id=1, total=5)] next_cursor=None — tên model sinh ra: "Page[InvoiceSummary]"

class Page2[T](BaseModel):           # cú pháp PEP 695 (Python 3.12+) cũng được hỗ trợ
    items: list[T]
```

FastAPI dùng `Page[InvoiceSummary]` làm `response_model` cho `GET /v1/invoices` — OpenAPI có schema riêng cho từng tham số kiểu.

### 6.2. `RootModel`: khi gốc không phải object

`RootModel[list[int]]` validate một mảng JSON ở gốc (`[1, 2]` → `.root == [1, 2]`). Với API mới, mình khuyên **gốc luôn là object** (`{"items": [...]}`) để sau này thêm trường (`next_cursor`, `warnings`) mà không phá client; `RootModel`/`TypeAdapter` để đọc định dạng có sẵn.

### 6.3. Model đệ quy và giới hạn độ sâu

```python
class Category(BaseModel):
    name: str
    children: list["Category"] = []
```

Dữ liệu đệ quy là cửa cho tấn công cạn tài nguyên: JSON lồng sâu hàng nghìn cấp. Thí nghiệm: một payload lồng ~300 cấp `{"children": [ ... ]}` bị **jiter từ chối** với lỗi `json_invalid: recursion limit exceeded` ở khoảng cấp thứ 100 — bộ parse có giới hạn độ sâu cứng. Tốt, nhưng vẫn nên đặt `max_length` cho danh sách con và giới hạn kích thước body ở tầng 0 (Module 11).

---

## 7. Case Mekong Cloud: `InvoiceIn` phiên bản 2

Ghép tất cả: tầng 1–2 trong Rust (Module 03), tầng 3 bằng validator Python có mã lỗi riêng. Mã đầy đủ, đã chạy thử:

```python
# invoice_v2.py — model hóa đơn phiên bản 2: đủ tầng 1–3 (Pydantic 2.14)
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

# TaxCode: xem mục 3.2
RATE = {"0": Decimal(0), "5": Decimal(5), "8": Decimal(8), "10": Decimal(10), "KCT": Decimal(0), "KKKNT": Decimal(0)}

def half_up(x: Decimal) -> int:
    return int(x.quantize(Decimal(1), rounding=ROUND_HALF_UP))

VND = Annotated[int, Field(ge=0, le=10**15)]
Qty = Annotated[Decimal, Field(gt=0, le=10**9, max_digits=15, decimal_places=4)]
VatRate = Literal["0", "5", "8", "10", "KCT", "KKKNT"]

class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

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

    @model_validator(mode="after")
    def _amount(self):
        expected = half_up(self.quantity * self.unit_price)
        if self.amount != expected:
            raise PydanticCustomError("line_amount", "amount phải bằng làm tròn(quantity × unit_price) = {expected}",
                                      {"expected": expected})
        return self

    @property
    def tax(self) -> int:
        return half_up(self.amount * RATE[self.vat_rate] / 100)

def _unique_line_no(lines: list[LineIn]) -> list[LineIn]:
    nos = [l.line_no for l in lines]
    if len(set(nos)) != len(nos):
        raise PydanticCustomError("line_no_duplicate", "line_no bị trùng")
    return lines

class InvoiceIn(RequestModel):
    series: Annotated[str, Field(pattern=r"^[0-9][A-Z0-9]{1,9}$")]
    number: Annotated[int, Field(ge=1, le=99_999_999)]
    seller_tax_code: TaxCode
    buyer: BuyerIn
    issued_at: AwareDatetime
    currency: Literal["VND"] = "VND"
    lines: Annotated[list[LineIn], Field(min_length=1, max_length=1000), AfterValidator(_unique_line_no)]
    total_before_tax: VND
    total_tax: VND
    total: VND

    @model_validator(mode="after")
    def _totals(self):
        before = sum(l.amount for l in self.lines)
        tax = sum(l.tax for l in self.lines)
        errors = []
        if self.total_before_tax != before:
            errors.append(f"total_before_tax phải là {before}")
        if self.total_tax != tax:
            errors.append(f"total_tax phải là {tax}")
        if self.total != self.total_before_tax + self.total_tax:
            errors.append("total phải bằng total_before_tax + total_tax")
        if errors:
            raise PydanticCustomError("invoice_totals", "Tổng tiền không khớp: {detail}", {"detail": "; ".join(errors)})
        return self
```

Chạy với một hóa đơn 2 dòng (3 ly cà phê 27.500đ thuế 8%; 1,5 phần bánh mì 18.353đ thuế 5% → `amount` = làm tròn 27.529,5 = 27.530; thuế 1.376,5 → **1.377**):

```text
OK  seller=0100233488  buyer=0314409058002  thuế từng dòng=[6600, 1377]  total=118007
```

Cố tình làm sai ba chỗ (MST sai checksum, `amount` dòng 2 lệch 1 đồng, `total_tax` lệch 1 đồng):

```text
('seller_tax_code',) tax_code_checksum  MST sai chữ số kiểm tra (cần 8)
('lines', 1)         line_amount        amount phải bằng làm tròn(quantity × unit_price) = 27530
```

Chỉ hai lỗi — lỗi tổng tiền **chưa** được báo vì model validator `after` của `InvoiceIn` không chạy khi trường con có lỗi (mục 1.4). Sửa hai lỗi đầu, gửi lại:

```text
() invoice_totals  Tổng tiền không khớp: total_tax phải là 7977; total phải bằng total_before_tax + total_tax
```

<!-- placeholder-invoice-v2 -->

<!-- fig:invoice-v2 -->
<figure markdown="span">
  ![Ba lần gửi một hóa đơn sai: lỗi trường được báo trước, lỗi tổng tiền chỉ xuất hiện khi mọi trường đã hợp lệ](assets/figures/04/invoice-v2.light.svg#only-light){ loading=lazy }
  ![Ba lần gửi một hóa đơn sai: lỗi trường được báo trước, lỗi tổng tiền chỉ xuất hiện khi mọi trường đã hợp lệ](assets/figures/04/invoice-v2.dark.svg#only-dark){ loading=lazy }
  <figcaption>Hình 4.7 — Ba lần gửi một hóa đơn sai: lỗi trường được báo trước, lỗi tổng tiền chỉ xuất hiện khi mọi trường đã hợp lệ.</figcaption>
</figure>
<!-- /fig -->

`InvoiceIn` v2 giờ phủ tầng 1–3. Còn tầng 4 (MST người bán thuộc tenant, số hóa đơn chưa dùng, idempotency) — Module 08 và 10.

---

## Lỗi thường gặp & cách xử lý

| Triệu chứng | Nguyên nhân gốc | Cách xử lý |
|---|---|---|
| Validator chạy sai thứ tự, chuẩn hóa chạy sau kiểm tra | Không hiểu mô hình củ hành của `Annotated` | Before chạy phải → trái, after chạy trái → phải; đặt chuẩn hóa ở ngoài cùng |
| `KeyError` trong `field_validator` khi đọc `info.data["x"]` | Trường `x` khai báo sau, hoặc đã lỗi | Dùng `info.data.get`; chuyển sang model validator `after` |
| Client không thấy lỗi tổng tiền dù tổng sai | Model `after` bị bỏ qua khi có lỗi trường | Bình thường; ghi trong tài liệu: sửa lỗi trường trước |
| Tổng thuế lệch 1 đồng giữa client và server | `round()` là half-even; float | `Decimal` + `ROUND_HALF_UP`; tài liệu hóa quy tắc |
| Lỗi trả về `value_error` chung chung | Ném `ValueError` | `PydanticCustomError("ma_rieng", "thông báo {x}", {"x": ...})` |
| Union chậm và lỗi trả về hàng chục mục khó hiểu | Smart union không tag | Thêm trường tag + `discriminator` |
| `int \| str` biến `"1"` thành `1` | `union_mode="left_to_right"` | Dùng smart (mặc định) hoặc tag |
| Ràng buộc viết bằng validator Python không hiện trong OpenAPI | JSON Schema không biết logic Python | Dùng `Field(gt=..., pattern=...)` khi có thể; thêm `__get_pydantic_json_schema__` |
| Validator gọi database | Trộn tầng 4 vào tầng 3 | Chuyển sang dependency/service (Module 08) |

## Tóm tắt (cheat-sheet)

- **after** (giá trị đã đúng kiểu) · **before** (thô, để chuẩn hóa) · **wrap** (bao quanh, có `handler`) · **plain** (thay thế).
- `Annotated` xếp chồng = củ hành: before ngoài → trong, after trong → ngoài.
- `info.data` = các trường trước đó đã hợp lệ; `context` để truyền tenant/ngôn ngữ; model `after` không chạy khi có lỗi trường.
- Chi phí: `Field(gt=0)` +0,3 ns; `AfterValidator` +33 ns; `WrapValidator` +172 ns mỗi lần gọi. Quy tắc có trong core → dùng core; quy tắc ngữ nghĩa → Python, đừng ngại.
- Kiểu tùy biến: `Annotated` có tên (đủ cho đa số) hoặc class + `__get_pydantic_core_schema__` + `PydanticCustomError` + `__get_pydantic_json_schema__`.
- Tiền: `int` VND hoặc `Decimal`, làm tròn `ROUND_HALF_UP` tường minh; không `round()`, không float. Làm tròn từng dòng vs tổng lệch tối đa $n/2 + 1/2$.
- Union: smart $O(k)$, nhiều lỗi; discriminated $O(1)$, một lỗi, OpenAPI `discriminator`. Đo được: ~3.560 → ~710 ns/phần tử, 9 → 1 lỗi.
- `Page[T]` generic cho phân trang; gốc API nên là object; jiter giới hạn độ sâu lồng nhau.

## Câu hỏi tự kiểm tra / phỏng vấn

1. Cho `Annotated[str, AfterValidator(a), BeforeValidator(b), AfterValidator(c), BeforeValidator(d)]`. Thứ tự chạy là gì?

    <details markdown="1"><summary>Gợi ý</summary>
    d → b → (str gốc) → a → c. Before chạy từ phải sang trái (ngoài vào trong), after chạy từ trái sang phải (trong ra ngoài).
    </details>

2. Khi nào dùng `wrap` thay vì cặp `before` + `after`?

    <details markdown="1"><summary>Gợi ý</summary>
    Khi cần xử lý phụ thuộc kết quả của validator gốc, ví dụ bắt lỗi của validator gốc để trả mặc định, đo thời gian, hay biến đổi cả trước và sau trong cùng một ngữ cảnh. Đổi lại wrap đắt nhất (~172 ns thêm mỗi lần đo được).
    </details>

3. Vì sao một model validator `after` kiểm tra tổng tiền không chạy khi `lines[3].amount` là chuỗi `"abc"`?

    <details markdown="1"><summary>Gợi ý</summary>
    `after` nhận instance đã đầy đủ, mọi trường hợp lệ. Khi có lỗi trường thì không tồn tại instance nào để truyền vào; Pydantic dừng và trả các lỗi trường.
    </details>

4. Viết ba dòng giải thích cho đội tích hợp POS vì sao tổng thuế của họ lệch 1 đồng so với server.

    <details markdown="1"><summary>Gợi ý</summary>
    Server làm tròn thuế từng dòng theo half-up (0,5 lên), dùng số thập phân chính xác. Có thể POS dùng `round()`/làm tròn ngân hàng (0,5 về chẵn) hoặc float, hoặc làm tròn trên tổng thay vì từng dòng. Ví dụ 27.530 × 5% = 1.376,5 → server 1.377.
    </details>

5. So sánh smart union và discriminated union về độ phức tạp, số lỗi, và JSON Schema.

    <details markdown="1"><summary>Gợi ý</summary>
    Smart: thử tới $k$ thành viên (có thể 2 lượt strict/lax), lỗi của mọi thành viên khi thất bại, schema `anyOf`. Discriminated: tra bảng theo tag $O(1)$, một lỗi có `loc` chứa tag, schema `oneOf` + `discriminator` (client sinh code chính xác).
    </details>

6. Thiết kế kiểu `Phone` cho số điện thoại Việt Nam (chấp nhận `0901 234 567`, `+84901234567`, lưu dạng E.164). Mức 1 hay mức 2?

    <details markdown="1"><summary>Gợi ý</summary>
    Mức 1 đủ: `Annotated[str, BeforeValidator(normalize), AfterValidator(check_prefix)]` với `normalize` bỏ khoảng trắng, đổi `0` đầu thành `+84`. Mức 2 nếu muốn kiểu riêng để code nghiệp vụ không nhầm với chuỗi thường và có mã lỗi + JSON Schema tùy chỉnh. Có thể cân nhắc `pydantic-extra-types` (dựa trên `phonenumbers`).
    </details>

7. Vì sao nên dùng `PydanticCustomError` thay vì `ValueError` trong validator?

    <details markdown="1"><summary>Gợi ý</summary>
    `ValueError` cho `type = value_error` chung, client không phân loại được. `PydanticCustomError` cho mã riêng (`tax_code_checksum`) và `ctx` có cấu trúc để dịch thông báo, thống kê lỗi tích hợp theo mã.
    </details>

8. Bất đẳng thức chặn độ lệch giữa "làm tròn từng dòng rồi cộng" và "cộng rồi làm tròn" là gì? Với 1.000 dòng, lệch tối đa bao nhiêu đồng?

    <details markdown="1"><summary>Gợi ý</summary>
    $|\sum \mathrm{round}(t_i) - \mathrm{round}(\sum t_i)| \le n/2 + 1/2$. Với 1.000 dòng: tối đa 500 đồng (thực tế thường nhỏ hơn nhiều vì sai số triệt tiêu, cỡ $\sqrt{n}$).
    </details>

9. Endpoint `GET /v1/invoices` trả về `Page[InvoiceSummary]`. OpenAPI sinh ra trông thế nào và vì sao generic tốt hơn viết tay `InvoicePage`, `BuyerPage`…?

    <details markdown="1"><summary>Gợi ý</summary>
    Pydantic sinh schema tên `Page_InvoiceSummary_` (hoặc tương tự) với `items: array of InvoiceSummary`. Generic tránh lặp code, đảm bảo mọi trang có cùng hình dạng (`items`, `next_cursor`), sửa một chỗ áp dụng mọi nơi.
    </details>

## Bài tập thực hành

1. **Thứ tự validator (CPU, 10 phút).** Tái tạo thí nghiệm mục 1.3 với 3 before, 2 after, 2 wrap; vẽ sơ đồ củ hành trước rồi chạy để kiểm chứng.
2. **TaxCode đầy đủ (CPU, 20 phút).** Hoàn thiện `TaxCode` mục 3.2, viết test cho: có dấu `-`, có khoảng trắng, nhánh `000`, tổng chia hết cho 11 (không có chữ số kiểm tra hợp lệ), và kiểm tra JSON Schema sinh ra. (Lab 01.)
3. **Đo union (CPU, 15 phút).** Chạy `scripts/bench/bench_validators.py`; thêm thành viên thứ 6, thứ 7 và vẽ chi phí theo $k$ cho smart và discriminated.
4. **Quy tắc làm tròn (CPU, 20 phút).** Sinh ngẫu nhiên 10.000 hóa đơn 12 dòng, tính tổng thuế theo bốn cách (half-up/half-even × từng dòng/tổng) và vẽ phân phối độ lệch. So với cận $n/2 + 1/2$.

## Tài liệu tham khảo

Tài liệu chính thức (tra cứu 10/2026, Pydantic 2.14):

- Pydantic — *Validators* (field/model validators, các chế độ, thứ tự). https://docs.pydantic.dev/latest/concepts/validators/
- Pydantic — *Unions* (smart mode, left_to_right, discriminated). https://docs.pydantic.dev/latest/concepts/unions/
- Pydantic — *Custom Types* (`__get_pydantic_core_schema__`). https://docs.pydantic.dev/latest/concepts/types/
- Pydantic — *Models: Generic models, RootModel*. https://docs.pydantic.dev/latest/concepts/models/
- Pydantic — *Validation Errors* và `PydanticCustomError`. https://docs.pydantic.dev/latest/errors/validation_errors/
- annotated-types. https://github.com/annotated-types/annotated-types
- pydantic-extra-types. https://github.com/pydantic/pydantic-extra-types
- OpenAPI Specification 3.1 — *Discriminator Object*. https://spec.openapis.org/oas/v3.1.0#discriminator-object
- Python docs — `decimal` (ROUND_HALF_UP, ROUND_HALF_EVEN); `round()`. https://docs.python.org/3/library/decimal.html
- python-stdnum — `stdnum.vn.mst`. https://arthurdejong.org/python-stdnum/doc/stdnum.vn.mst

Nền tảng:

- Goldberg, D. (1991). *What Every Computer Scientist Should Know About Floating-Point Arithmetic*. ACM Computing Surveys 23(1). https://dl.acm.org/doi/10.1145/103162.103163
- PEP 593 (Annotated), PEP 695 (Type Parameter Syntax). https://peps.python.org/
