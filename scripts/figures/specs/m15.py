MD = "docs/15-pydantic-cho-llm.md"
MODULE = "15"
PREFIX = "15"

FIGS = [
    ("<!-- placeholder-four-ways -->", "four-ways",
     "Bốn cách lấy dữ liệu có cấu trúc từ LLM, từ yếu tới mạnh về mức bảo đảm."),
    ("<!-- placeholder-masking -->", "masking",
     "Constrained decoding: ở mỗi bước, token nào làm hỏng ngữ pháp bị gán xác suất 0 trước khi lấy mẫu."),
    ("<!-- placeholder-modes -->", "modes",
     "Số đo thật: tỷ lệ output hợp lệ theo schema Pydantic ở ba chế độ sinh, cùng model và cùng prompt."),
    ("<!-- placeholder-overhead -->", "overhead",
     "Số đo thật: chi phí của constrained decoding — compile grammar, thời gian mỗi token, thời gian tính mask."),
    ("<!-- placeholder-tools -->", "tools",
     "Tool calling: chữ ký hàm Python → model Pydantic → JSON Schema gửi cho LLM → arguments được validate trước khi gọi."),
    ("<!-- placeholder-retry -->", "retry",
     "Số đo thật: validate–retry đưa lỗi Pydantic trở lại prompt; số case hợp lệ sau mỗi lượt."),
    ("<!-- placeholder-partial -->", "partial",
     "Số đo thật: validate từng tiền tố của output đang stream; model 'preview' với trường tùy chọn hợp lệ ở mọi bước."),
    ("<!-- placeholder-security -->", "security",
     "Output hợp lệ về cú pháp vẫn có thể độc: các lớp kiểm soát sau validate."),
    ("<!-- placeholder-pipeline -->", "pipeline",
     "Pipeline ai-gateway đầy đủ: grammar → stream → validate từng phần → validate cuối → nghiệp vụ."),
]
