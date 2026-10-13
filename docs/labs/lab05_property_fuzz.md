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

{{LAB05_PROPS}}

## Phần 2 — Fuzz theo schema (`test_fuzz_api.py`)

```python
schema = schemathesis.openapi.from_asgi("/openapi.json", app)

@schema.parametrize()
@settings(max_examples=50, deadline=None)
def test_api_khong_5xx_va_dung_schema(case, auth_headers):
    case.call_and_validate(headers=auth_headers)
```

`conftest.py` khởi tạo state của app (DB file tạm, khóa JWT) và phát token đủ scope. Không có token thì hầu hết request dừng ở 401, và fuzz không đi sâu được vào logic.

{{LAB05_FUZZ}}

## Câu hỏi

1. Vì sao endpoint `POST /v1/invoices` khai báo `responses={401: {}, 403: {}, 409: {}, 422: {}}`? Thử xóa và chạy lại Schemathesis.
2. Schemathesis sinh body ngẫu nhiên theo **JSON Schema**. Nó có sinh được hóa đơn **hợp lệ về nghiệp vụ** (MST đúng checksum, tổng khớp) không? Hệ quả cho độ phủ của fuzz là gì? (Module 12: kết hợp với strategy tự viết ở phần 1.)
