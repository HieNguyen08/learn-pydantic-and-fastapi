# Lab 06 — Structured output, validate–retry và SSE

> ~30 phút · Sau Module 15 · Lời giải: `labs/lab06_llm_structured_sse/`

## Mục tiêu

Xây phần lõi của `ai-gateway`: nhận tin nhắn của khách, nhờ LLM trích **hóa đơn nháp** có cấu trúc, validate bằng Pydantic, retry có giới hạn, và stream bản nháp từng phần qua **SSE**. Lab dùng **LLM giả lập tất định** (`fake_llm.py`) để chạy nhanh và test được. Phần mở rộng thay bằng model thật trên CPU.

`FakeLLM` tái hiện đúng các lỗi đo được trên Qwen2.5-0.5B ở Module 15:

- lần gọi đầu trả `"vat_rate": "8%"` (sai `Literal`) và bọc JSON trong ```` ```json ````;
- lần sau, khi đã nhận thông điệp lỗi, trả đúng;
- với tin nhắn chứa chữ "khó", model sai **cả 3 lần**: lỗi có hệ thống, retry vô ích.

## Bước 1 — Model (`models.py`)

`InvoiceDraft` (trường bắt buộc, `Literal`, `pattern`, validator checksum MST) và `DraftPreview` (mọi trường tùy chọn, dùng khi stream). Vì sao cần hai model? (Module 15, mục 6: 8% so với 100% tiền tố validate được.)

## Bước 2 — `POST /v1/drafts`: validate–retry

Vòng lặp tối đa 3 lần: gọi LLM → bóc fence → `model_validate_json` → nếu lỗi, thêm lượt `assistant` (output sai) và `user` (lỗi Pydantic, **không kèm input**) rồi gọi lại. Hết lượt thì trả **422** với danh sách lỗi. Không đoán, không "sửa hộ".

## Bước 3 — `GET /v1/drafts/stream`: SSE

Mỗi chunk từ LLM: cộng vào buffer → `TypeAdapter(DraftPreview).validate_json(buf, experimental_allow_partial="trailing-strings")` → `ServerSentEvent(event="partial", id=…, data=…)`. Cuối cùng validate bằng `InvoiceDraft` và gửi `final` hoặc `error`.

```bash
cd labs/lab06_llm_structured_sse && pytest -q
# ...                                                                      [100%]
# 3 passed
```

Output thật của stream (rút gọn):

```text
event: partial
data: {}
id: 1

event: partial
data: {"buyer_name": "Công ty "}
id: 2

event: partial
data: {"buyer_name": "Công ty TNHH Sông Hậ"}
id: 3
…
event: final
data: {"buyer_name": "Công ty TNHH Sông Hậu", "buyer_tax_code": "0100109106", "vat_rate": "8",
       "lines": [{"name": "cà phê", "quantity": 2, "unit_price": 29000}, {"name": "bánh mì", "quantity": 1, "unit_price": 25000}]}
id: 19
```

## Mở rộng — LLM thật trên CPU

`scripts/bench/bench_llm.py` có lớp `LLM` dùng transformers + xgrammar. Thay `FakeLLM.complete` bằng một hàm gọi `LLM.gen(messages, mode)`:

1. `mode="prompt"`: đo tỉ lệ hợp lệ và tỉ lệ retry thành công trên 10 tin nhắn.
2. `mode="schema"` (constrained decoding theo `InvoiceDraft.model_json_schema()`): tỉ lệ hợp lệ là bao nhiêu? Lỗi còn lại thuộc loại nào? (Gợi ý: grammar không biểu diễn được checksum MST.)
3. Dùng `transformers.TextIteratorStreamer` để có stream thật cho endpoint SSE.
