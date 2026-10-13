# SYLLABUS — ranh giới nội dung từng module (tránh trùng lặp)

Mỗi module chỉ đi sâu phần của mình; chủ đề thuộc module khác thì nhắc 1–2 câu và dẫn chiếu "(xem Module NN)".

| # | File | Chủ đề | Thời lượng |
|---|------|--------|-----------|
| 00 | 00-tong-quan-va-bai-toan.md | Lộ trình, case Mekong Cloud, bản đồ kiến thức, hệ sinh thái & số liệu | 20' |
| 01 | 01-kieu-du-lieu-va-validation.md | Lý thuyết kiểu & validation: gradual typing, parse-don't-validate, LangSec | 45' |
| 02 | 02-http-rest-asgi.md | HTTP, REST, WSGI/ASGI, event loop, async/await, GIL | 50' |
| 03 | 03-pydantic-v2-kien-truc.md | Pydantic v2: kiến trúc pydantic-core, core schema, lax/strict, lỗi | 50' |
| 04 | 04-validators-kieu-tuy-bien-union.md | Validator, Annotated, kiểu tùy biến, union & discriminator, generic | 50' |
| 05 | 05-serialization-json-schema-settings.md | Serialization, alias, JSON Schema, pydantic-settings | 45' |
| 06 | 06-hieu-nang-pydantic.md | Đo & tối ưu hiệu năng validation (benchmark thật) | 45' |
| 07 | 07-fastapi-vong-doi-request.md | FastAPI: vòng đời request, routing, tham số, response model, OpenAPI | 50' |
| 08 | 08-dependency-injection.md | Dependency injection: lý thuyết, đồ thị dependency, yield, scope, override | 40' |
| 09 | 09-async-dong-thoi-hieu-nang.md | Async & đồng thời: threadpool, chặn event loop, Little, M/M/c, worker | 55' |
| 10 | 10-database-va-persistence.md | SQLAlchemy async, session/transaction, pool, N+1, migration, idempotency | 50' |
| 11 | 11-bao-mat-api.md | OAuth2/JWT, mật khẩu, OWASP API Top 10, BOLA, rate limit, DoS | 50' |
| 12 | 12-testing-va-chat-luong.md | Test pyramid, override, property-based, fuzz theo schema, tiến hóa API | 45' |
| 13 | 13-production-va-observability.md | Triển khai, process model, probe, OTel, SLO, retry/backoff, metastable | 50' |
| 14 | 14-capstone-thiet-ke-he-thong.md | Capstone: thiết kế invoice-api + ai-gateway, câu hỏi system design | 55' |
| 15 | 15-pydantic-cho-llm.md | Chuyên đề: structured output, tool calling, constrained decoding, SSE | 50' |
| L | labs/ | 6 lab chạy trên CPU | ~2 giờ |
| S | slides/ | Slide seminar (reveal.js + PDF) | 60–90' |

## Chi tiết

### 00 — Tổng quan
Vì sao dữ liệu ở ranh giới hệ thống là nguồn lỗi số 1. Lịch sử Pydantic (2017 → v2 Rust 2023 → 2.14) và FastAPI (2018 → 0.143), Starlette 1.0 (03/2026). Số liệu hệ sinh thái (lượt tải, khảo sát JetBrains/PSF). Hai dịch vụ của Mekong Cloud và vì sao chọn hai workload trái ngược. Bản đồ kiến thức, lịch học, cách dùng slide.

### 01 — Kiểu dữ liệu & validation (lý thuyết)
Kiểu là gì (tập giá trị + phép toán), static vs dynamic, strong vs weak, nominal vs structural (Protocol), soundness. Gradual typing (Siek & Taha 2006), type `Any`, "Is sound gradual typing dead?" (Takikawa 2016) → vì sao Python chọn *unsound, erased* hints. Lịch sử PEP 484/526/544/585/593/604/646/695/747/649. Bằng chứng thực nghiệm: Gao 2017 (15%), Khan 2021 (15% mypy), Di Grazia & Pradel 2022. Static check không thay được runtime validation ở ranh giới: tin cậy, nguồn dữ liệu. "Parse, don't validate" (King 2019) – smart constructor, kiểu bất biến. LangSec (Sassaman, Patterson, Bratus 2011/2013): shotgun parser, máy nhận dạng đủ mạnh, parser differential. Postel và RFC 9413. Lý thuyết tập/lattice của coercion (lax vs strict là hai hàm parse khác nhau). Ứng dụng: biên dịch quy tắc hóa đơn thành kiểu.

### 02 — HTTP, REST & ASGI
HTTP semantics (RFC 9110): method, an toàn, idempotent, status code, header, content negotiation. REST (Fielding 2000) – các ràng buộc, thực tế "REST-ish", Richardson maturity. Idempotency-Key. WSGI (PEP 3333) vs ASGI (scope/receive/send), lifespan. Event loop: selector/epoll, coroutine, task, await; mô hình C10K, threads vs events (Ousterhout 1996, von Behren 2003). GIL, free-threading 3.14 (PEP 703/779). Uvicorn: httptools/h11, uvloop. Vòng đời một request từ socket tới handler (sơ đồ).

### 03 — Pydantic v2: kiến trúc
BaseModel, Field, model_validate/model_validate_json, model_construct. Kiến trúc hai tầng: Python sinh *core schema* → pydantic-core (Rust, PyO3) dựng cây validator. Bảng coercion lax/strict, `strict=True`, `extra`. ValidationError: cấu trúc lỗi (type, loc, msg, input, url). TypeAdapter, dataclasses, TypedDict. Forward refs, rebuild, defer_build. Bất biến (frozen), copy. Tham số config quan trọng.

### 04 — Validators, kiểu tùy biến & union
Field/model validators mode before/after/wrap/plain; thứ tự chạy trong Annotated (pipeline). `ValidationInfo`, context. Kiểu tùy biến: Annotated + validator, `__get_pydantic_core_schema__`. Ràng buộc (constraints) và vì sao nên đẩy xuống core. Union: smart mode (thuật toán chấm điểm exactness), left_to_right, discriminated union (tagged union, O(1) dispatch, lỗi gọn hơn), callable discriminator. RootModel, generic model, model đệ quy. Bất biến liên trường (tổng tiền hóa đơn).

### 05 — Serialization, JSON Schema & settings
model_dump (python/json mode), include/exclude, by_alias, exclude_unset/defaults/none, field/model serializer, computed_field, alias/validation_alias/serialization_alias, AliasChoices/AliasPath. Round-trip. JSON Schema: dialect 2020-12, mode validation vs serialization, $defs, nền tảng hình thức (Pezoa et al. 2016), các khác biệt validator. pydantic-settings: nguồn & thứ tự ưu tiên, SecretStr, nested delimiter, 12-factor.

### 06 — Hiệu năng Pydantic
Phương pháp benchmark (warm-up, lặp, trung vị, IQR, nhiễu). Benchmark thật: Pydantic v2 vs dataclasses thủ công vs msgspec vs marshmallow vs attrs+cattrs trên payload hóa đơn. `model_validate_json` vs `json.loads` + `model_validate`. Chi phí dựng schema (import-time), TypeAdapter tái sử dụng, `defer_build`. Validator Python vs ràng buộc core. Mô hình chi phí tuyến tính theo số dòng hàng; Amdahl: validation chiếm bao nhiêu % một request. Khi nào cần msgspec/bỏ qua validation (model_construct) và rủi ro.

### 07 — FastAPI: vòng đời request
Kiến trúc FastAPI trên Starlette. Từ chữ ký hàm → `Dependant` → validation tham số (path/query/header/cookie/body/form/file). Body nhúng, nhiều body. response_model: lọc trường (chống lộ dữ liệu), serialization. Status code, exception handler, 422 vs 400. Middleware (thứ tự, ASGI middleware thuần vs BaseHTTPMiddleware). Router, prefix, tag, version. Sinh OpenAPI 3.1 và docs. Streaming response, JSONL, SSE tích hợp (`fastapi.sse`). Lifespan. Quy trình xử lý một `POST /v1/invoices` (sơ đồ từng bước).

### 08 — Dependency injection
IoC & DI (Fowler 2004), service locator vs DI. Đồ thị dependency là DAG, giải theo thứ tự topo, cache trong một request (`use_cache`). Dependency `yield` (setup/teardown, thứ tự LIFO, exception propagation), scope. Security dependencies, `Security` + scopes. Lớp làm dependency, dependency có tham số. Global/router dependencies. `dependency_overrides` cho test. Chi phí DI. Anti-pattern.

### 09 — Async, đồng thời & hiệu năng
`async def` vs `def` trong FastAPI: event loop vs threadpool (anyio, mặc định 40 luồng). Chặn event loop (benchmark thật: latency khi có `time.sleep`), CPU-bound trong async. Định luật Little, mô hình M/M/1 và M/M/c, độ trễ tăng phi tuyến theo utilization; chọn số worker/luồng. Universal Scalability Law. Đo thật: def vs async def vs async-blocking với nhiều mức concurrency. Process model: uvicorn workers, gunicorn; số worker = f(CPU). Backpressure, timeout, giới hạn concurrency (semaphore). Tail latency (Dean & Barroso 2013).

### 10 — Database & persistence
SQLAlchemy 2.x: Core vs ORM, async engine/session, session-per-request bằng dependency yield, transaction boundary. Pool: kích thước, timeout, công thức HikariCP, liên hệ Little. N+1 và các anti-pattern ORM (Yang et al. ICSE 2018), selectinload/joinedload. Tách model ORM và schema Pydantic (from_attributes). Migration với Alembic, expand/contract không downtime. Idempotency key: bảng, unique constraint, trạng thái. Multi-tenant: tenant_id + RLS Postgres. Outbox pattern.

### 11 — Bảo mật API
Mô hình đe dọa cho API. Xác thực: OAuth 2.0/2.1, OIDC, RFC 9700; JWT (RFC 7519, RFC 8725: alg none, algorithm confusion, exp/aud/iss), API key cho máy. Băm mật khẩu: Argon2id (RFC 9106), tham số OWASP, toán chi phí brute-force. Phân quyền: BOLA, BOPLA/mass assignment, BFLA (OWASP API Top 10 2023) và cách Pydantic + DI chặn từng loại. Rate limiting: token bucket/GCRA (toán), theo tenant. DoS qua payload: giới hạn kích thước, độ sâu, số phần tử. CORS, header bảo mật, SSRF. Bí mật & cấu hình.

### 12 — Testing & chất lượng
Test pyramid/trophy cho API. TestClient vs httpx.AsyncClient + ASGITransport, lifespan trong test. `dependency_overrides`, DB test với transaction rollback. Property-based testing (QuickCheck 2000, Hypothesis 2019): thuộc tính round-trip, bất biến, oracle; shrinking; ví dụ MST check digit. Fuzz theo schema: Schemathesis (2022), RESTler (2019), EvoMaster; khảo sát Golmohammadi et al. 2023. Contract testing & tiến hóa API: breaking change trong OpenAPI (nghiên cứu USI 2022/2024), versioning, deprecation. Kiểm tra kiểu tĩnh trong CI. Mutation testing (giới thiệu).

### 13 — Production & observability
Đóng gói (Docker multi-stage), process model trên Kubernetes (1 process/pod vs nhiều worker), liveness/readiness/startup probe, graceful shutdown (SIGTERM, drain), lifespan. Cấu hình. Log có cấu trúc + correlation ID. Tracing (Dapper 2010 → OpenTelemetry), telemetry tích hợp của FastAPI. Metric RED/USE, histogram & percentile. SLO, error budget (toán burn rate). Retry với exponential backoff + jitter, timeout, circuit breaker; metastable failure (Bronson 2021). Load shedding. Versioning & deprecation khi vận hành.

### 14 — Capstone
Thiết kế end-to-end theo format system design: yêu cầu, ước lượng (dùng đúng số của case), API contract (OpenAPI), mô hình dữ liệu, kiến trúc (mermaid), luồng xử lý chi tiết `POST /v1/invoices` và luồng webhook → LLM → SSE, idempotency, multi-tenant, bảo mật, quan sát, kế hoạch test, rollout, rủi ro. Bộ 12–15 câu hỏi phỏng vấn system design có lời giải.

### 15 — Pydantic cho LLM (chuyên đề)
Structured output: prompt-only vs JSON mode vs strict schema vs constrained decoding. Lý thuyết constrained decoding: FSM/regex (Willard & Louf 2023), CFG/pushdown (XGrammar 2024), che logits. JSONSchemaBench (2025), "Let Me Speak Freely?" (2024) – thứ tự trường & lý luận. Tool/function calling: schema từ Pydantic, BFCL (2025). Vòng lặp validate–retry, chi phí kỳ vọng. Thư viện: Instructor, PydanticAI, MCP. Streaming JSON từng phần (partial validation) qua SSE. Bảo mật: không tin output LLM, validate như input người dùng.

### labs/
1. Mô hình hóa hóa đơn bằng Pydantic (MST, VAT, tổng tiền) + test.
2. Benchmark các thư viện validation (tái tạo số liệu Module 06).
3. `invoice-api` hoàn chỉnh: DI, SQLite async, idempotency, JWT, BOLA.
4. Đo đồng thời: def vs async vs blocking (tái tạo số liệu Module 09).
5. Property-based testing + fuzz theo OpenAPI.
6. LLM structured output với validate–retry (LLM giả lập) + SSE.
