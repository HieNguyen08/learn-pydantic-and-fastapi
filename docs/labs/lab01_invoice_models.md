# Lab 01 — Mô hình hóa hóa đơn bằng Pydantic

> ~25 phút · Sau Module 04 · Lời giải: `labs/lab01_invoice_models/`

## Mục tiêu

Viết model `Invoice` mà **mọi hóa đơn sai đều không tạo được đối tượng**: MST sai chữ số kiểm tra, tiền là chuỗi, thời điểm không có múi giờ, tổng không khớp, trường lạ. Rồi kiểm chứng bằng test ví dụ và test thuộc tính.

## Bước 1 — Kiểu MST (Module 01, 04)

Viết `check_tax_code(v: str) -> str` theo quy tắc:

- bỏ dấu `-` và khoảng trắng; độ dài 10 hoặc 13, toàn chữ số;
- 7 chữ số giữa (vị trí 3–9) không được toàn `0`; với 13 số, 3 số cuối không được là `000`;
- chữ số thứ 10 = $10 - (\sum_{i=1}^{9} w_i d_i \bmod 11)$ với $w = (31, 29, 23, 19, 17, 13, 7, 5, 3)$; kết quả 10 nghĩa là tiền tố không hợp lệ.

Rồi khai báo `TaxCode = Annotated[str, Field(min_length=10, max_length=17), AfterValidator(check_tax_code)]`. Dùng `PydanticCustomError` để lỗi có **mã riêng** (`tax_code_checksum`, `tax_code_format`), vì client sẽ dựa vào mã chứ không dựa vào câu chữ.

**Kiểm tra**: `check_tax_code("0100109106")` trả về chính nó; `"0100109107"` ném lỗi `tax_code_checksum`.

## Bước 2 — Tiền và làm tròn (Module 04)

- `VND = Annotated[int, Field(ge=0, le=10**15, strict=True)]`. Vì sao `strict`? (Gợi ý: Module 12, Schemathesis tìm ra `false` được nhận là `0`.)
- `half_up(x: Decimal) -> int` làm tròn nửa lên. **Không** dùng `round()`.
- `line_tax(amount, rate)` = `half_up(amount × rate / 100)`; `"KCT"` và `"KKKNT"` có thuế suất 0.

**Dự đoán trước khi chạy**: `round(52.5)` bằng bao nhiêu? Còn `half_up(Decimal("52.5"))`?

## Bước 3 — Model

- `Line`: `name`, `quantity: Decimal` (`gt=0`, tối đa 4 chữ số thập phân), `unit_price: VND`, `vat_rate: Literal[...]`, `amount: VND`. Thêm `model_validator(mode="after")` kiểm `amount == half_up(quantity × unit_price)`.
- `Invoice`: `seller_tax_code: TaxCode`, `buyer`, `issued_at: AwareDatetime`, `lines` (1–1000 phần tử), ba trường tổng. Thêm validator kiểm tổng **theo từng dòng rồi cộng**.
- `model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)` cho mọi model.

**Kiểm tra**: `python invoice.py` in đúng 5 lỗi cho hóa đơn mẫu sai:

```text
seller_tax_code              tax_code_checksum      MST sai chữ số kiểm tra
buyer.name                   string_too_short       String should have at least 1 character
issued_at                    timezone_aware         Input should have timezone info
lines.0.unit_price           int_type               Input should be a valid integer
lines.0.vat_rate             literal_error          Input should be '0', '5', '8', '10', 'KCT' or 'KKKNT'
```

**Câu hỏi**: hóa đơn mẫu còn có tổng sai, nhưng lỗi `invoice_totals` không xuất hiện. Vì sao? (Module 04: validator `after` của model chỉ chạy khi mọi trường đã hợp lệ.)

## Bước 4 — Test

Chạy `pytest -q`: **10 passed**. Bộ test gồm:

- 1 test hợp lệ, 6 test lỗi (`parametrize` theo mã lỗi), 1 test round-trip JSON;
- 2 test thuộc tính (Hypothesis): **đổi một chữ số của MST hợp lệ → bị phát hiện**, và **thuế làm tròn nửa lên** so với oracle `Fraction`.

## Mở rộng

1. Đổi `half_up` thành `round()` và chạy lại: test nào đỏ, với phản ví dụ nào? (Module 12 đã đo: `(525, 10)`.)
2. Thêm hỗ trợ hóa đơn **điều chỉnh** (tổng có thể âm): sửa kiểu ở đâu để không làm yếu ràng buộc của hóa đơn thường?
