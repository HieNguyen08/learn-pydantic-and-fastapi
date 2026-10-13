MD = "docs/14-capstone-thiet-ke-he-thong.md"
MODULE = "14"
PREFIX = "14"

FIGS = [
    ("<!-- placeholder-load -->", "load",
     "Ước lượng tải theo giờ của invoice-api từ giả định của case; đường đứt là mức thiết kế 500 req/s."),
    ("<!-- placeholder-datamodel -->", "datamodel",
     "Mô hình dữ liệu của invoice-api; mọi bảng mang tenant_id và chịu RLS."),
    ("<!-- placeholder-budget -->", "budget",
     "Số đo thật: ngân sách latency của một POST /v1/invoices; transaction DB chiếm phần lớn, Pydantic chưa tới 1%."),
    ("<!-- placeholder-capacity -->", "capacity",
     "Số đo thật: thông lượng và p99 theo tải của invoice-api đầy đủ, với hai tầng truy cập DB và 1–2 tiến trình."),
    ("<!-- placeholder-db-layer -->", "db-layer",
     "Số đo thật: CPU phía Python của cùng một transaction qua SQLAlchemy text() và asyncpg thuần."),
    ("<!-- placeholder-aiflow -->", "aiflow",
     "Luồng ai-gateway: webhook trả 202 ngay, worker gọi LLM, draft đẩy qua Redis tới SSE."),
    ("<!-- placeholder-rollout -->", "rollout",
     "Rollout theo bậc canary có cổng SLO, migration expand trước và contract sau."),
    ("<!-- placeholder-risks -->", "risks",
     "Ma trận rủi ro: khả năng xảy ra và tác động."),
]
