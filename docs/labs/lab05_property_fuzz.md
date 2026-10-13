# Lab 05 — Property-based testing và fuzz theo OpenAPI

> ~20 phút · Sau Module 12 · Lời giải: `labs/lab05_property_fuzz/`

## Mục tiêu

1. Viết **strategy Hypothesis sinh hóa đơn hợp lệ theo cấu trúc** (MST đúng checksum, `amount` khớp, tổng khớp), rồi kiểm hai thuộc tính trên model Lab 01.
2. Fuzz `invoice-api` của Lab 03 bằng **Schemathesis** ngay trong pytest, có token xác thực.

## Phần 1 — Thuộc tính (`test_properties.py`)

- `mst()`: `@st.composite` sinh 9 chữ số rồi **tính** chữ số kiểm tra. Đừng sinh 10 chữ số ngẫu nhiên rồi lọc: chỉ ~1/10 thỏa, Hypothesis sẽ báo `filter_too_much`.
- `line`: số lượng, đơn giá, thuế suất ngẫu nhiên; `amount` **tính ra** từ chúng.
- `invoice()`: các dòng + tổng tính từ các dòng.

Hai thuộc tính:

1. **Mọi hóa đơn sinh ra đều hợp lệ và round-trip JSON** (`model_dump_json` → `model_validate_json` → bằng nhau).
2. **Sửa tổng một lượng bất kỳ ≥ 1 → luôn bị từ chối** với lỗi `invoice_totals`.

```bash
cd labs/lab05_property_fuzz && pytest -q test_properties.py
```

Kết quả (`pytest -q test_properties.py --hypothesis-show-statistics`):

```text
test_hoa_don_sinh_ra_luon_hop_le_va_round_trip:
    - 200 passing, 0 failing, and 45 invalid test cases
    * 16.33%, Retried draw from text(...0123456789..., min_size=9, max_size=9).filter(lambda s: s[2:9] != '0000000')
    * 4.49%, gave up because: failed to satisfy assume() in mst (line 20)
test_sua_tong_thi_bi_tu_choi:
    - 200 passing, 0 failing, and 75 invalid test cases
2 passed in 1.95s
```

Đọc thống kê: "invalid" là các lần `assume()` hoặc `filter` loại bỏ input. Ở đây ~5–11% ca bị loại vì chữ số kiểm tra bằng 10, và ~16% phải rút lại vì `filter`. Hypothesis cố ý sinh nhiều chuỗi toàn số 0 (một giá trị biên), nên `filter(s[2:9] != "0000000")` bị chạm thường xuyên hơn bạn nghĩ. Tỉ lệ này vẫn chấp nhận được. Khi nó vượt quá ~50%, Hypothesis sẽ báo `FailedHealthCheck`, và đó là lúc phải **sinh đúng ngay từ đầu** thay vì lọc.

## Phần 2 — Fuzz theo schema (`test_fuzz_api.py`)

```python
schema = schemathesis.openapi.from_asgi("/openapi.json", app)

@schema.parametrize()
@settings(max_examples=50, deadline=None)
def test_api_khong_5xx_va_dung_schema(case, auth_headers):
    case.call_and_validate(headers=auth_headers)
```

`conftest.py` khởi tạo state của app (DB file tạm, khóa JWT) và phát token đủ scope. Không có token thì hầu hết request dừng ở 401, và fuzz không đi sâu được vào logic.

### Kết quả: Schemathesis tìm ra bốn lỗi trong chính lời giải Lab 03

Lần chạy đầu tiên, khi viết lab này, **thất bại**. Mỗi lỗi dưới đây là một phát hiện thật, đã được sửa trong `labs/lab03_invoice_api/app/main.py`:

| # | Request Schemathesis gửi | Kết quả | Nguyên nhân | Cách sửa |
|---|---|---|---|---|
| 1 | `GET /v1/invoices/0` không kèm token | 401, nhưng OpenAPI chỉ khai báo 200/404/422 | thiếu `responses` cho lỗi xác thực | `responses={401: {}, 403: {}, 404: {}}` |
| 2 | `GET /v1/invoices/9223372036854775808` | **500**: `OverflowError: Python int too large to convert to SQLite INTEGER` | `invoice_id: int` không có cận trên, $2^{63}$ tràn BIGINT | `Annotated[int, Path(ge=1, le=2**63 - 1)]` |
| 3 | `POST /v1/invoices` với body là byte rác | 400 `There was an error parsing the body`, chưa khai báo | FastAPI trả 400 khi body không phải JSON | thêm `400: {}` vào `responses` |
| 4 | `POST` với `seller_tax_code: "0000000000"`, `quantity: ""` | 422, nhưng body **khớp JSON Schema** | schema không biểu diễn được checksum MST; `Decimal` có ràng buộc sinh ra `{"type": "string"}` không kèm pattern | không sửa API: loại riêng check `positive_data_acceptance` (có chú thích lý do) |

Lỗi 2 đáng chú ý nhất: một số nguyên hợp lệ hoàn toàn theo kiểu Python lại làm sập request. Không ai viết test ví dụ với $2^{63}$, nhưng fuzzer thử giá trị biên một cách có hệ thống.

Lỗi 4 không phải bug mà là **khoảng cách giữa schema và validator**, đúng chủ đề Module 05 và câu hỏi 2 bên dưới. Check `positive_data_acceptance` đòi mọi body hợp lệ theo schema đều phải được nhận. API cố ý chặt hơn schema, nên test loại riêng check này, và mọi check còn lại vẫn chạy:

```python
from schemathesis.specs.openapi.checks import positive_data_acceptance

case.call_and_validate(headers=auth_headers, excluded_checks=[positive_data_acceptance])
```

Sau khi sửa, hai lần chạy liên tiếp đều qua:

```text
$ pytest -q
....                                                                     [100%]
4 passed in 6.00s
```

## Câu hỏi

1. Vì sao endpoint `POST /v1/invoices` khai báo `responses={400: {}, 401: {}, 403: {}, 409: {}, 422: {}}`? Thử xóa và chạy lại Schemathesis.
2. Schemathesis sinh body ngẫu nhiên theo **JSON Schema**. Nó có sinh được hóa đơn **hợp lệ về nghiệp vụ** (MST đúng checksum, tổng khớp) không? Hệ quả cho độ phủ của fuzz là gì? (Module 12: kết hợp với strategy tự viết ở phần 1.)
