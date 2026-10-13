MD = "docs/13-production-va-observability.md"
MODULE = "13"
PREFIX = "13"

FIGS = [
    ("<!-- placeholder-process -->", "process",
     "Hai process model: một Uvicorn mỗi pod (Kubernetes) và nhiều worker mỗi máy."),
    ("<!-- placeholder-probes -->", "probes",
     "Ba loại probe trả lời ba câu hỏi khác nhau; phụ thuộc bên ngoài chỉ thuộc readiness."),
    ("<!-- placeholder-shutdown -->", "shutdown",
     "Trình tự graceful shutdown trên Kubernetes và số đo thật của uvicorn khi nhận SIGTERM."),
    ("<!-- placeholder-pillars -->", "pillars",
     "Ba trụ quan sát và cách nối chúng: exemplar dẫn tới trace, trace_id dẫn tới log."),
    ("<!-- placeholder-obs-cost -->", "obs-cost",
     "Số đo thật: chi phí mỗi request của log, metric và telemetry tích hợp của FastAPI."),
    ("<!-- placeholder-percentiles -->", "percentiles",
     "Trung bình các p99 không phải p99; độ chính xác của histogram_quantile phụ thuộc bucket."),
    ("<!-- placeholder-slo -->", "slo",
     "Error budget còn lại theo thời gian với các burn rate dùng để cảnh báo."),
    ("<!-- placeholder-backoff -->", "backoff",
     "Mô phỏng: tải tạo ra và thời gian hoàn thành của các chiến lược retry khi 100 client tranh một tài nguyên."),
    ("<!-- placeholder-metastable -->", "metastable",
     "Mô phỏng metastable failure: sau khi sự cố hết, retry không chờ giữ goodput bằng 0; backoff có budget và load shedding thì hồi phục."),
    ("<!-- placeholder-shedding -->", "shedding",
     "Số đo thật: load shedding dưới tải 1,5 lần năng lực — không giới hạn, --limit-concurrency của uvicorn, và giới hạn in-flight ở tầng ứng dụng."),
]
