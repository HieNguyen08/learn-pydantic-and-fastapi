# STYLE GUIDE — Pydantic & FastAPI Masterclass (dành cho người viết module)

Khóa học: **"Pydantic & FastAPI từ nền tảng đến hệ thống production — xoay quanh hai dịch vụ thật của Mekong Cloud: API hóa đơn điện tử và AI gateway"**.
Tổng thời lượng: ~12 giờ phần lõi (Module 00–14, Lab 01–05) và ~1,5 giờ phần mở rộng (Module 15, Lab 06). Mỗi module là một "buổi giảng" 40–55 phút. Có kèm bộ slide seminar (`docs/slides/`).

## 1. Người học

- Hiếu, sinh viên năm cuối Khoa học Máy tính (HCMUT), đã làm đồ án NLU/NER/RAG tự host, từng làm Rails full-stack, đã học xong RAG Masterclass.
- Sắp vào dự án nền tảng LLM: vLLM, FastAPI (healthcheck, log, history, observability), SSE streaming, gRPC, MCP server, LangGraph, system design.
- Máy cá nhân: Windows + WSL2 + Docker, RTX 4050 6 GB. **Mọi lab chạy được trên CPU.**
- Biết lập trình, cấu trúc dữ liệu, xác suất thống kê, mạng máy tính mức đại học → được phép đi sâu lý thuyết (hệ kiểu, ngôn ngữ hình thức, lý thuyết hàng đợi), nhưng mỗi công thức phải có trực giác + ví dụ số.

## 2. Ngôn ngữ & giọng văn

- Viết **tiếng Việt**, giữ thuật ngữ tiếng Anh (validator, serializer, dependency injection, event loop, coroutine…); lần đầu xuất hiện thì giải thích ngắn.
- Giọng giảng viên/chuyên gia: rõ ràng, có chính kiến kỹ thuật ("trong thực tế mình khuyên…"), không màu mè, không emoji, không marketing.

## 3. Định dạng

- Markdown MkDocs Material. Toán: `$...$` inline và `$$...$$` block (dòng trống trước và sau khối `$$`).
- Sơ đồ luồng: khối ```mermaid. Hình dữ liệu/đồ thị: sinh bằng `scripts/figures/chNN.py` (bản sáng + tối), chèn bằng `insert.py`.
- Code: Python 3.13+, Pydantic 2.14, FastAPI 0.143 (tính đến 10/2026); ngắn, **chạy được**, comment tiếng Việt. Code nào in kết quả thì kết quả trong bài phải là kết quả chạy thật.
- Bảng để so sánh lựa chọn (trade-off). Khối đáp án dùng `<details markdown="1">`.

## 4. Cấu trúc bắt buộc của mỗi module

```
# Module NN — Tên module
> Thời lượng: ~X phút · Mức độ: … · Tiên quyết: Module …

## Mục tiêu học tập        (4–7 gạch đầu dòng, đo được)
## 1. … 2. …               (các phần nội dung)
   - Mỗi kỹ thuật: Vấn đề → Trực giác → Lý thuyết/toán (định nghĩa, công thức) → Ví dụ số
     → Code chạy được → Cách vận hành bên trong (quy trình, sơ đồ) → Trade-off / khi nào KHÔNG dùng.
   - Ít nhất 1 khối "Case thực tế" mỗi phần lớn: Mekong Cloud hoặc case công khai có nguồn.
## Lỗi thường gặp & cách xử lý      (bảng: Triệu chứng | Nguyên nhân gốc | Cách xử lý)
## Tóm tắt (cheat-sheet)
## Câu hỏi tự kiểm tra / phỏng vấn  (8–12 câu, đáp án trong <details>)
## Bài tập thực hành               (2–4 bài)
## Tài liệu tham khảo              (paper có năm + venue/arXiv ID; docs chính thức; chỉ link đã kiểm tra)
```

Mỗi module 6.000–10.000 từ và **ít nhất 8 hình** (đồ thị số liệu, sơ đồ quy trình, sơ đồ kiến trúc). Mục tiêu "dễ hiểu bằng hình": mọi cơ chế vận hành bên trong (vòng đời request, pipeline validation, event loop, pool kết nối…) đều có sơ đồ.

## 5. Case study xuyên suốt (giả định thống nhất — dùng đúng các con số này)

**Mekong Cloud** — doanh nghiệp SaaS B2B hư cấu (phần mềm bán hàng, kho, hóa đơn điện tử; cùng công ty trong RAG Masterclass). Các con số dưới đây là **giả định để học**.

### Dịch vụ A — `invoice-api` (API hóa đơn điện tử, CPU + validation nặng)

- Khách hàng: **3.000 doanh nghiệp (tenant)**, ~**12.000 máy POS/ERP** tích hợp qua REST.
- Tải: ~**1,8 triệu request/ngày** (60% tạo hóa đơn `POST`, 35% tra cứu `GET`, 5% khác). 85% tải rơi vào 12 giờ bán hàng → trung bình giờ bán ≈ **35 req/s**; giờ cao điểm trưa/tối ×4 ≈ **140 req/s**; ngày cuối tháng ×3 nữa ≈ **420 req/s**. **Thiết kế cho 500 req/s**, SLO p99 ≤ **300 ms** cho `POST /v1/invoices`.
- Payload: hóa đơn trung bình **12 dòng hàng, ~5 KB JSON**; endpoint batch tối đa **500 hóa đơn/request**.
- Ràng buộc nghiệp vụ: mã số thuế (MST) 10 hoặc 13 chữ số có chữ số kiểm tra; thuế suất GTGT ∈ {0%, 5%, 8%, 10%, KCT, KKKNT} (8% là mức giảm tạm thời theo NQ 204/2025/QH15, hiệu lực đến 31/12/2026); tiền VND là số nguyên; tổng tiền phải khớp tổng các dòng; POS hay gửi lại khi mất mạng → **idempotency**; tuyệt đối không lộ hóa đơn tenant khác (BOLA); hóa đơn đã ký không sửa, chỉ điều chỉnh/thay thế.

### Dịch vụ B — `ai-gateway` (I/O + streaming, latency dài)

- Backend của hệ thống AI tư vấn khách hàng qua Zendesk (RAG Masterclass): ~**1.500 ticket/ngày → ~3.000 lượt chạy pipeline/ngày**, đỉnh ~0,4 lượt/s.
- Mỗi lượt gọi LLM mất **5–30 s**; output là JSON có schema (Pydantic) → validate, retry khi sai schema.
- UI nội bộ cho ~**60 agent CS** đồng thời, nhận draft qua **SSE**; tool cho agent qua **MCP**.
- Ràng buộc: webhook Zendesk phải trả lời nhanh (< 10 s) và idempotent; prompt injection trong email; PII.

Hai dịch vụ cố ý **trái ngược nhau** (nhiều request ngắn, CPU-bound vs ít request dài, I/O-bound) để mọi quyết định thiết kế (async hay sync, số worker, pool, cache, timeout) đều phải lập luận bằng số.

### Stack tham chiếu (tính đến 10/2026)

Python 3.13/3.14 · Pydantic 2.14 · pydantic-core 2.50 · FastAPI 0.143 · Starlette 1.8 · Uvicorn 0.54 · SQLAlchemy 2.1 (async) + asyncpg · PostgreSQL · Redis · OpenTelemetry · Docker/Kubernetes.

### Máy đo benchmark

Mọi số đo trong khóa được chạy thật trên **container 4 vCPU Intel Xeon 2,8 GHz, Python 3.13**, script nằm trong `scripts/bench/`. Ghi rõ đó là số đo trên máy này; chạy lại trên máy bạn sẽ ra số khác nhưng **tỷ lệ** thường giữ nguyên.

## 6. Nguồn & độ chính xác

- Dùng WebSearch/WebFetch để kiểm tra paper (tên, tác giả, năm, venue/arXiv), số benchmark công bố, tính năng/phiên bản thư viện, văn bản pháp lý. Ghi "tính đến 10/2026" khi nêu hiện trạng.
- Hành vi thư viện: kiểm chứng bằng cách **chạy code** với phiên bản đã cài, không dựa trí nhớ.
- Không bịa con số. Ước lượng thì ghi "ước lượng" và cách tính.
- Bản quyền: diễn đạt lại bằng lời của mình; trích nguyên văn tối đa 1 câu ngắn/nguồn.
