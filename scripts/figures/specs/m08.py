MD = "docs/08-dependency-injection.md"
MODULE = "08"
PREFIX = "8"

FIGS = [
    ("<!-- placeholder-ioc -->", "ioc",
     "Handler tự lấy phụ thuộc so với được tiêm phụ thuộc qua chữ ký hàm."),
    ("<!-- placeholder-dag -->", "dag",
     "Đồ thị dependency của ví dụ /ok và thứ tự chạy ghi nhận được; mỗi nút chạy một lần nhờ cache trong request."),
    ("<!-- placeholder-yield -->", "yield",
     "Thứ tự setup/teardown đo được của hai dependency yield với scope khác nhau quanh một response streaming."),
    ("<!-- placeholder-patterns -->", "patterns",
     "Bốn mẫu dependency thường dùng."),
    ("<!-- placeholder-dep-cost -->", "dep-cost",
     "Số đo thật trong tiến trình: chi phí request theo số dependency và cách khai báo; độ dốc là chi phí mỗi dependency."),
    ("<!-- placeholder-overrides -->", "overrides",
     "dependency_overrides thay đúng một nút của đồ thị khi test."),
    ("<!-- placeholder-case -->", "case",
     "Đồ thị dependency của invoice-api."),
]
