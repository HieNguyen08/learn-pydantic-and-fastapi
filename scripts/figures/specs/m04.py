MD = "docs/04-validators-kieu-tuy-bien-union.md"
MODULE = "04"
PREFIX = "4"

FIGS = [
    ("<!-- placeholder-onion -->", "onion",
     "Mô hình củ hành của Annotated và thứ tự chạy ghi nhận được khi chạy thật."),
    ("<!-- placeholder-validator-cost -->", "validator-cost",
     "Số đo thật: chi phí mỗi phần tử của sáu cách cài cùng quy tắc «> 0». Ràng buộc trong Rust gần như miễn phí; mỗi validator Python thêm hàng chục đến hàng trăm nano-giây."),
    ("<!-- placeholder-custom-type -->", "custom-type",
     "Luồng validate của kiểu TaxCode: kiểm tra độ dài trong Rust, chuẩn hóa và checksum trong Python, lỗi có mã riêng, JSON Schema tùy chỉnh."),
    ("<!-- placeholder-rounding -->", "rounding",
     "Mô phỏng 10.000 hóa đơn: độ lệch tổng thuế giữa half-up và round() của Python (trái), và giữa làm tròn từng dòng với làm tròn tổng (phải)."),
    ("<!-- placeholder-union-cost -->", "union-cost",
     "Số đo thật: chi phí smart union tăng theo vị trí của thành viên khớp, discriminated union thì không đổi (trái); tốc độ và số lỗi của bốn cách khai báo (phải)."),
    ("Pydantic dựng một **bảng băm** `method → validator`", "union-flow",
     "Smart union thử lần lượt các thành viên; discriminated union tra bảng theo thẻ. Khác biệt cũng thể hiện trong OpenAPI."),
    ("<!-- placeholder-invoice-v2 -->", "invoice-v2",
     "Ba lần gửi một hóa đơn sai: lỗi trường được báo trước, lỗi tổng tiền chỉ xuất hiện khi mọi trường đã hợp lệ."),
]
