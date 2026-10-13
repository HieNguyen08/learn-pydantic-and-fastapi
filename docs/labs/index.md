# Labs — thực hành

> Tổng thời lượng: ~2 giờ (Lab 01–05) + ~30 phút (Lab 06) · Mọi lab chạy trên CPU · Lời giải tham khảo nằm trong thư mục [`labs/`](https://github.com/HieNguyen08/learn-pydantic-and-fastapi/tree/main/labs) của repo

Mỗi lab đi theo cùng một nhịp:

1. **Dự đoán**: trước khi chạy, viết ra con số hoặc hành vi bạn nghĩ sẽ thấy, dựa trên module tương ứng.
2. **Làm**: viết code theo từng bước. Mỗi bước có một điểm kiểm tra (test hoặc output mẫu).
3. **Đo / kiểm**: chạy test và script. So với dự đoán.
4. **Giải thích**: chênh lệch giữa dự đoán và thực tế đến từ đâu?

| Lab | Nội dung | Sau module | Thời lượng |
|---|---|---|---|
| [01 · Mô hình hóa hóa đơn](lab01_invoice_models.md) | MST có chữ số kiểm tra, tiền strict, làm tròn half-up, tổng tiền, test ví dụ + thuộc tính | 04 | 25' |
| [02 · Benchmark validation](lab02_benchmark_validation.md) | `model_validate_json` vs `json.loads` + `model_validate`, `TypeAdapter` dùng lại, đo đúng cách | 06 | 15' |
| [03 · invoice-api hoàn chỉnh](lab03_invoice_api.md) | DI, SQLite async, idempotency, JWT, BOLA, cấp số liên tục, test bằng `AsyncClient` | 10–11 | 40' |
| [04 · Đo đồng thời](lab04_concurrency.md) | `async def` / `def` / chặn event loop dưới tải; kiểm định luật Little | 09 | 20' |
| [05 · Property-based & fuzz](lab05_property_fuzz.md) | Hypothesis sinh hóa đơn hợp lệ; Schemathesis fuzz Lab 03 theo OpenAPI | 12 | 20' |
| [06 · Structured output & SSE](lab06_llm_structured_sse.md) | validate–retry với LLM giả lập, SSE partial, tùy chọn chạy model thật | 15 | 30' |

## Chuẩn bị môi trường

```bash
python -m venv .venv && source .venv/bin/activate          # Windows: dùng WSL2
pip install "pydantic>=2.14" "fastapi>=0.143" "uvicorn[standard]" "sqlalchemy[asyncio]" aiosqlite \
            "pyjwt[crypto]" httpx pytest pytest-asyncio hypothesis schemathesis
cd labs/lab01_invoice_models && pytest -q                 # kiểm tra: 10 passed
```

Lab 06 có phần tùy chọn chạy LLM thật trên CPU, cần thêm `torch` (bản CPU), `transformers`, `xgrammar`. Model Qwen2.5-0.5B-Instruct được tải tự động (~1 GB).

!!! tip "Số đo trên máy bạn sẽ khác"
    Output mẫu trong các lab được chạy trên container 4 vCPU, Python 3.13. Hãy so **tỷ lệ** và **hình dạng**, không so con số tuyệt đối.
