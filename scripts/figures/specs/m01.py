MD = "docs/01-kieu-du-lieu-va-validation.md"
MODULE = "01"
PREFIX = "1"

FIGS = [
    ("<!-- placeholder-spectrum -->", "spectrum",
     "Phổ các cách gõ kiểu theo đảm bảo lúc chạy và chi phí. Pydantic đặt cast có kiểm tra đúng một lần tại ranh giới."),
    ("<!-- placeholder-evidence -->", "evidence",
     "Trái: tỷ lệ lỗi đã sửa mà type checker phát hiện được (Gao et al. 2017; Khan et al. 2021). Phải: tỷ lệ commit có annotation (Di Grazia & Pradel 2022)."),
    ("<!-- placeholder-parse-vs-validate -->", "parse-vs-validate",
     "Shotgun validation để lại tác dụng phụ dở dang; parse ở cửa từ chối toàn bộ trước khi có bất kỳ tác dụng phụ nào."),
    ("<!-- placeholder-chomsky -->", "chomsky",
     "Các quy tắc của hóa đơn trên phân cấp Chomsky và bộ nhận dạng tương ứng."),
    ("<!-- placeholder-differential -->", "differential",
     "Kết quả chạy thật bảng ở mục 5.4: các ô vàng là chỗ bộ parse nhận dữ liệu phi chuẩn hoặc đổi nghĩa — nguồn gốc của parser differential."),
    ("<!-- placeholder-postel -->", "postel",
     "Tập đầu vào được chấp nhận ở chế độ strict và lax; phần chênh lệch là nơi cần quyết định thiết kế."),
    ("<!-- placeholder-accumulate -->", "accumulate",
     "Số lượt gửi–sửa của client theo số lỗi độc lập trong payload: fail-fast so với tích lũy lỗi."),
    ("<!-- placeholder-layers -->", "layers",
     "Năm tầng quy tắc của POST /v1/invoices, nơi thực thi và chi phí điển hình của từng tầng."),
]
