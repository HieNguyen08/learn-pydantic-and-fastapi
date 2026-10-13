MD = "docs/03-pydantic-v2-kien-truc.md"
MODULE = "03"
PREFIX = "3"

FIGS = [
    ("<!-- placeholder-architecture -->", "architecture",
     "Kiến trúc hai tầng: lúc định nghĩa class, Python sinh core schema và pydantic-core dựng cây validator/serializer bằng Rust; mỗi request chỉ chạy cây Rust."),
    ("<!-- placeholder-validator-tree -->", "validator-tree",
     "Cây validator của Invoice. Chỉ các nút có validator Python (model_validator, AfterValidator…) mới quay lại trình thông dịch."),
    ("<!-- placeholder-json-path -->", "json-path",
     "Số đo thật, hóa đơn 12 dòng: parse + validate bằng model_validate_json tốn ngang chỉ parse bằng json.loads, và nhanh gấp đôi json.loads + model_validate."),
    ("<!-- placeholder-build-cost -->", "build-cost",
     "Số đo thật: thời gian định nghĩa model theo số trường so với thời gian validate một instance (nhãn ×N là tỷ lệ giữa hai thời gian)."),
    ("<!-- placeholder-coercion -->", "coercion",
     "Bảng chuyển đổi được sinh bằng cách chạy TypeAdapter(T).validate_python/validate_json với strict=False/True trên Pydantic 2.14.1."),
    ("<!-- placeholder-error-anatomy -->", "error-anatomy",
     "Một phần tử của ValidationError.errors() và cách ánh xạ sang mục lỗi trong Problem Details."),
    ("<!-- placeholder-extra -->", "extra",
     "Ba chế độ extra với cùng một đầu vào có trường gõ sai tên."),
    ("<!-- placeholder-required -->", "required",
     "Kiểu và tính bắt buộc là hai chiều độc lập trong Pydantic v2."),
    ("<!-- placeholder-typeadapter -->", "typeadapter",
     "Số đo thật: dựng TypeAdapter(list[Invoice]) trong mỗi request làm chi phí tăng nhiều lần so với adapter tạo sẵn."),
    ("<!-- placeholder-invoice-v1 -->", "invoice-v1",
     "Phạm vi của InvoiceIn phiên bản 1 trên năm tầng quy tắc của Module 01."),
]
