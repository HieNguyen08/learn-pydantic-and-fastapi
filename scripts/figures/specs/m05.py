MD = "docs/05-serialization-json-schema-settings.md"
MODULE = "05"
PREFIX = "5"

FIGS = [
    ("<!-- placeholder-dump-modes -->", "dump-modes",
     "Ba biểu diễn của cùng một model; Decimal, datetime và SecretStr đổi dạng khi sang JSON."),
    ("<!-- placeholder-roundtrip -->", "roundtrip",
     "Computed field có mặt trong output nên model có extra='forbid' không đọc lại được dữ liệu chính nó xuất ra; tách model vào/ra để tránh."),
    ("<!-- placeholder-alias -->", "alias",
     "AliasChoices và AliasPath cho phép nhận nhiều tên trên dây nhưng chỉ xuất một tên."),
    ("<!-- placeholder-schema-modes -->", "schema-modes",
     "Cùng một model, hai JSON Schema: những gì client phải gửi và những gì server chắc chắn trả về."),
    ("<!-- placeholder-schema-diff -->", "schema-diff",
     "Kết quả thí nghiệm mục 3.4: JSON Schema bỏ sót mọi quy tắc tầng 3, còn chế độ lax nhận những chuỗi số mà schema từ chối."),
    ("<!-- placeholder-ser-cost -->", "ser-cost",
     "Số đo thật: chi phí serialize theo số dòng hàng của năm cách làm."),
    ("<!-- placeholder-settings -->", "settings",
     "Thứ tự ưu tiên nguồn cấu hình, mỗi bậc kèm kết quả quan sát được trong thí nghiệm."),
    ("<!-- placeholder-in-out -->", "in-out",
     "Ba hình dạng của một hóa đơn: model đầu vào, hàng ORM và model đầu ra."),
]
