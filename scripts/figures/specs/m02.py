MD = "docs/02-http-rest-asgi.md"
MODULE = "02"
PREFIX = "2"

FIGS = [
    ("<!-- placeholder-methods -->", "methods",
     "Tính chất của các method HTTP theo RFC 9110."),
    ("<!-- placeholder-idempotency -->", "idempotency",
     "Trái: luồng gửi lại an toàn nhờ Idempotency-Key. Phải: số hóa đơn trùng kỳ vọng mỗi ngày nếu thiếu cơ chế này, theo tỷ lệ mất response p."),
    ("<!-- placeholder-rest -->", "rest",
     "Sáu ràng buộc REST và lựa chọn của invoice-api."),
    ("<!-- placeholder-pagination -->", "pagination",
     "Số đo thật: thời gian lấy một trang 50 hóa đơn theo số thứ tự trang, phân trang offset so với cursor (keyset)."),
    ("<!-- placeholder-asgi -->", "asgi",
     "Server, middleware và ứng dụng đều nói chung một giao diện ASGI; request và response là các sự kiện qua receive/send."),
    ("<!-- placeholder-event-loop -->", "event-loop",
     "Một vòng của event loop asyncio và hệ quả của một lời gọi chặn."),
    ("<!-- placeholder-mem -->", "mem",
     "Số đo thật: RSS tăng thêm và thời gian tạo khi giữ n luồng hệ điều hành so với n task asyncio đang chờ."),
    ("<!-- placeholder-gil -->", "gil",
     "Số đo thật: chia cùng một khối lượng CPU thuần Python cho luồng (chung GIL) và tiến trình."),
    ("<!-- placeholder-uvicorn-variants -->", "uvicorn-variants",
     "Số đo thật: throughput của cùng ứng dụng với bốn tổ hợp bộ phân tích HTTP và event loop của Uvicorn."),
    ("<!-- placeholder-journey -->", "journey",
     "Chín bước của một request POST /v1/invoices, tô màu theo thành phần chịu trách nhiệm."),
]
