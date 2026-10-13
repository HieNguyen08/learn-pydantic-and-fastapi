MD = "docs/12-testing-va-chat-luong.md"
MODULE = "12"
PREFIX = "12"

FIGS = [
    ("<!-- placeholder-pyramid -->", "pyramid",
     "Các tầng test cho một API FastAPI, chi phí đo được và ví dụ quy tắc ở từng tầng."),
    ("<!-- placeholder-clients -->", "clients",
     "Số đo thật: chi phí mỗi request khi gọi app bằng TestClient, AsyncClient + ASGITransport và uvicorn thật."),
    ("<!-- placeholder-db-isolation -->", "db-isolation",
     "Số đo thật: ba chiến lược cô lập database giữa các test, và cơ chế transaction + savepoint."),
    ("<!-- placeholder-pbt -->", "pbt",
     "Vòng lặp property-based testing: sinh input, kiểm thuộc tính, tìm phản ví dụ và thu nhỏ."),
    ("<!-- placeholder-pbt-results -->", "pbt-results",
     "Số đo thật: ba lỗi cài sẵn đều lọt qua test ví dụ và đều bị Hypothesis tìm ra."),
    ("<!-- placeholder-fuzz -->", "fuzz",
     "Fuzz theo schema với Schemathesis và những lỗi nó tìm ra trên app mẫu."),
    ("<!-- placeholder-mutation -->", "mutation",
     "Số đo thật: điểm đột biến của ba bộ test và những đột biến sống sót."),
    ("<!-- placeholder-breaking -->", "breaking",
     "Số đo thật: phát hiện breaking change giữa hai phiên bản OpenAPI do FastAPI sinh."),
    ("<!-- placeholder-ci -->", "ci",
     "Pipeline kiểm thử của invoice-api trên mỗi pull request."),
]
