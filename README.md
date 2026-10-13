# Pydantic & FastAPI Masterclass

**Pydantic & FastAPI từ nền tảng đến hệ thống production — xoay quanh hai dịch vụ của Mekong Cloud: API hóa đơn điện tử và AI gateway.**

Website: https://hienguyen08.github.io/learn-pydantic-and-fastapi/

Giáo trình tiếng Việt ~12 giờ phần lõi và ~1,5 giờ chuyên đề: 16 module lý thuyết (lý thuyết + sơ đồ cơ chế + số liệu đo thật + case thực tế) và 6 lab chạy trên CPU.

| Phần | Module |
|---|---|
| I · Nền tảng | 00 Tổng quan & bài toán · 01 Kiểu dữ liệu & validation · 02 HTTP, REST & ASGI |
| II · Pydantic | 03 Kiến trúc v2 · 04 Validator, kiểu tùy biến & union · 05 Serialization, JSON Schema & settings · 06 Hiệu năng |
| III · FastAPI | 07 Vòng đời request · 08 Dependency injection · 09 Async & đồng thời · 10 Database · 11 Bảo mật API |
| IV · Vận hành | 12 Testing · 13 Production & observability · 14 Capstone thiết kế hệ thống |
| V · Chuyên đề | 15 Pydantic cho LLM |
| Thực hành | Lab 01–06 (`docs/labs/`) |

## Chạy website trên máy

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-docs.txt
mkdocs serve            # mở http://127.0.0.1:8000
```

## Số liệu benchmark và hình minh họa

```bash
pip install pydantic fastapi "uvicorn[standard]" msgspec marshmallow attrs cattrs orjson \
            "sqlalchemy[asyncio]" aiosqlite asyncpg alembic argon2-cffi bcrypt "pyjwt[crypto]" redis \
            hypothesis schemathesis opentelemetry-sdk prometheus-client httpx matplotlib numpy
# Module 15 (LLM, chạy trên CPU, tải Qwen2.5-0.5B-Instruct ≈ 1 GB lần đầu)
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install transformers xgrammar
# Module 10–13 cần thêm PostgreSQL (PG_DSN) và Redis (REDIS_URL), xem đầu bench_db.py / bench_security.py
python -m venv .venv-v1 && .venv-v1/bin/pip install "pydantic<2"   # để so sánh với v1
scripts/bench/run_all.sh                     # ≈ 20 phút, ghi scripts/bench/results/*.json
cd scripts/figures && python ch03.py         # sinh lại hình của một module từ số liệu
```

Mọi số đo trong bài chạy trên container 4 vCPU, Python 3.13; trên máy khác số tuyệt đối sẽ khác nhưng tỷ lệ thường giữ nguyên.

## Cấu trúc repo

```
docs/                 nội dung website (Markdown)
  00-…md … 15-…md     các module lý thuyết
  assets/figures/     hình SVG (bản sáng + tối), sinh bằng scripts/figures
  labs/               lab thực hành
scripts/bench/        benchmark và kết quả JSON
scripts/figures/      code vẽ hình (chNN.py) và spec chèn hình (specs/mNN.py)
notes/                style guide và syllabus
.github/workflows/    check.yml (build --strict trên mọi PR), deploy.yml (GitHub Pages khi push main)
```

## Lưu ý

- Mekong Cloud là công ty hư cấu; số liệu quy mô là giả định để học.
- Phiên bản thư viện, tính năng và văn bản pháp lý cập nhật tính đến 10/2026 (Pydantic 2.14, FastAPI 0.143, Starlette 1.8).
