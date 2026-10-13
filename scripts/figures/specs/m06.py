MD = "docs/06-hieu-nang-pydantic.md"
MODULE = "06"
PREFIX = "6"

FIGS = [
    ("<!-- placeholder-noise -->", "noise",
     "Số đo thật: cùng một phép đo chạy trong 8 tiến trình độc lập. Min ổn định hơn trung vị trong một lần chạy, nhưng giữa các tiến trình vẫn dao động ±15%."),
    ("<!-- placeholder-libs-12 -->", "libs-12",
     "Số đo thật: hóa đơn 12 dòng, chín cách làm, hai mức kiểm tra (thang log)."),
    ("<!-- placeholder-scaling -->", "scaling",
     "Số đo thật: thời gian validate theo số dòng hàng (log–log); các đường gần như song song."),
    ("<!-- placeholder-cost-model -->", "cost-model",
     "Hai tham số của mô hình chi phí tuyến tính cho từng cách làm."),
    ("<!-- placeholder-breakdown -->", "breakdown",
     "Số đo thật: phân rã chi phí Pydantic cho một hóa đơn theo bốn bước."),
    ("<!-- placeholder-amdahl -->", "amdahl",
     "Định luật Amdahl với số liệu của invoice-api: thay thư viện validation chỉ cho vài phần trăm, trong khi đổi bộ phân tích HTTP cho ~1,7 lần."),
    ("<!-- placeholder-checklist -->", "checklist",
     "Lợi ích đo được của bốn tối ưu mặc định, tính trên phần mã liên quan."),
    ("<!-- placeholder-batch -->", "batch",
     "Batch lớn chặn event loop; thiết kế giới hạn kích thước và xử lý bất đồng bộ của invoice-api."),
]
