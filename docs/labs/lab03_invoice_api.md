# Lab 03 — invoice-api hoàn chỉnh

> ~40 phút · Sau Module 10–11 · Lời giải: `labs/lab03_invoice_api/`

## Mục tiêu

Dựng `invoice-api` thu gọn nhưng đủ các cơ chế của Module 07–11 và kiểm từng cơ chế bằng test:

| Cơ chế | Module | Test |
|---|---|---|
| Model Lab 01 làm body; 422 với mã lỗi riêng | 04, 07 | `test_validation_422_mst_sai` |
| Session-per-request, `Depends(scope="function")`, commit trước 201 | 08, 10 | mọi test ghi |
| JWT EdDSA, `Principal` validate bằng Pydantic, 401 vs 403 | 11 | `test_khong_token_401_thieu_scope_403` |
| Chống BOLA: truy vấn luôn có `tenant_id`, trả 404 | 10, 11 | `test_bola_tenant_khac_nhan_404` |
| Idempotency: `INSERT … ON CONFLICT DO NOTHING` trước, lưu response | 10 | `test_idempotency_phat_lai_va_khac_payload` |
| Cấp số liên tục: `UPDATE … RETURNING` cuối transaction | 10 | `test_so_hoa_don_lien_tuc_khi_dong_thoi` |

Lab dùng **SQLite + aiosqlite** để chạy được ở mọi nơi. Ở production, thay bằng PostgreSQL và thêm RLS (Module 10). Mã SQL đã chọn để chạy trên cả hai.

## Cấu trúc

```text
lab03_invoice_api/
  app/db.py         ORM (InvoiceRow, LineRow, Series, IdempotencyKey), Database.session() kiểu yield
  app/security.py   KeyPair (khóa Ed25519 sinh lúc khởi động), Principal, current_principal
  app/main.py       lifespan, dependency, hai endpoint
  tests/            conftest.py (AsyncClient + lifespan_context + DB file tạm), test_api.py
```

## Các bước

1. **Dependency session** (`app/main.py`): bọc `Database.session()` thành `db_session`, rồi khai báo `DB = Annotated[AsyncSession, Depends(db_session, scope="function")]`. Hỏi: chuyện gì xảy ra với `scope="request"` nếu `COMMIT` thất bại (Module 08, 10)?
2. **Xác thực**: `Writer = Annotated[Principal, Security(current_principal, scopes=["invoice:write"])]`. `current_principal` cố định `algorithms=["EdDSA"]`, kiểm `aud`, `iss`, `exp`.
3. **`POST /v1/invoices`** theo đúng thứ tự:
    1. băm `body.model_dump_json()` (model **đã** validate);
    2. giành `Idempotency-Key`; nếu khóa đã có chủ thì phát lại response, hoặc trả 422 nếu khác payload;
    3. ghi hóa đơn với `number = NULL`;
    4. cấp số bằng `UPDATE series … RETURNING`;
    5. lưu response vào bảng idempotency;
    6. trả `InvoiceOut`.
4. **`GET /v1/invoices/{id}`**: `select(...).options(selectinload(...)).where(id == …, tenant_id == p.tenant_id)`. Quan hệ khai báo `lazy="raise"`: thử bỏ `selectinload` để thấy lỗi (Module 10).
5. Chạy test:

```bash
cd labs/lab03_invoice_api && pytest -q
# ......                                                                   [100%]
# 6 passed
```

## Hai cái bẫy đã gặp khi viết lab này

- **`sqlite+aiosqlite:///:memory:` trong test**: SQLAlchemy dùng **một** kết nối chung cho DB trong bộ nhớ, nên 20 transaction "đồng thời" chạy trên cùng một kết nối và lẫn vào nhau. Test cấp số đồng thời fail với `UNIQUE constraint failed`. Cách sửa: mỗi test một **file** SQLite tạm (`tmp_path`).
- **Số tạm `0` khi chèn hóa đơn**: hai transaction cùng chèn `(tenant, series, 0)` sẽ va ràng buộc `UNIQUE`. Dùng `NULL` (ràng buộc unique bỏ qua `NULL`) cho tới khi cấp số thật.

## Chạy thử bằng tay

```bash
uvicorn app.main:app --reload
# mở http://127.0.0.1:8000/docs — để thử với token, dùng fixture `token` trong tests/conftest.py làm mẫu
```

## Mở rộng

1. Thêm `PATCH /v1/invoices/{id}` với model `InvoicePatch(extra="forbid")` chỉ cho sửa `buyer_name` khi hóa đơn chưa ký (Module 11, BOPLA).
2. Thêm `GET /v1/invoices?cursor=…&limit=…` phân trang keyset (Module 02), kèm test "không trùng, không sót" khi có hóa đơn mới chèn giữa hai trang.
3. Chuyển sang PostgreSQL (`DATABASE_URL=postgresql+asyncpg://…`), bật RLS như `scripts/bench/capstone_app.py`, và chạy lại toàn bộ test.
