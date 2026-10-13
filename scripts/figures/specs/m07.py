MD = "docs/07-fastapi-vong-doi-request.md"
MODULE = "07"
PREFIX = "7"

FIGS = [
    ("<!-- placeholder-dependant -->", "dependant",
     "Lúc khai báo route, FastAPI phân tích chữ ký hàm thành cây Dependant và dựng sẵn body field, response field, schema OpenAPI."),
    ("<!-- placeholder-pipeline -->", "pipeline",
     "Chồng ứng dụng ASGI của Starlette (ngoài vào trong) và năm bước bên trong một route FastAPI, đọc từ mã nguồn 0.143 / Starlette 1.8."),
    ("<!-- placeholder-response -->", "response",
     "Số đo thật trong tiến trình: chi phí một request theo cách khai báo body và response."),
    ("<!-- placeholder-errors -->", "errors",
     "Định dạng 422 mặc định (có trường input phản chiếu dữ liệu) so với Problem Details theo RFC 9457."),
    ("<!-- placeholder-middleware -->", "middleware",
     "Số đo thật: throughput theo số lớp middleware trên server (trái) và chi phí mỗi lớp đo trong tiến trình (phải)."),
    ("<!-- placeholder-streaming -->", "streaming",
     "Stream bản nháp từ ai-gateway: mảnh đầu tiên đến sau khoảng một giây thay vì chờ cả 25 giây; định dạng SSE trên dây."),
    ("<!-- placeholder-profile -->", "profile",
     "Số đo thật: thời gian tự thân của một request POST /invoices gom theo thư viện."),
    ("<!-- placeholder-case -->", "case",
     "Các phần của POST /v1/invoices và module phụ trách từng phần."),
]
