MD = "docs/00-tong-quan-va-bai-toan.md"
MODULE = "00"
PREFIX = "0"

FIGS = [
    ("<!-- placeholder-trust -->", "trust-boundaries",
     "Ranh giới tin cậy: dữ liệu từ POS, webhook, LLM hay file cấu hình đều đi qua một cổng parse; dữ liệu sai bị từ chối tại cổng thay vì làm sập phần bên trong."),
    ("<!-- placeholder-timeline -->", "timeline",
     "Các mốc chính của type hint Python, Pydantic, Starlette và FastAPI (2014–10/2026)."),
    ("<!-- placeholder-ecosystem -->", "ecosystem",
     "Trái: tỷ lệ dùng framework web trong Python Developers Survey (vạch chấm: năm trước). Phải: lượt tải Pydantic theo hai nguồn với hai cách đếm khác nhau."),
    ("<!-- placeholder-fermi -->", "fermi",
     "Chuỗi nhân Fermi cho invoice-api: từ 1,8 triệu request/ngày đến tải thiết kế 500 req/s (số giả định)."),
    ("<!-- placeholder-load-profile -->", "load-profile",
     "Hồ sơ tải theo giờ dựng từ các giả định của case: đỉnh trưa ~140 req/s, ngày cuối tháng ~420 req/s."),
    ("<!-- placeholder-two-workloads -->", "two-workloads",
     "Hai workload trên mặt phẳng (tốc độ đến, thời gian mỗi request). Đường chấm là số request đồng thời theo định luật Little — chủ đề chính của Module 09."),
    ("<!-- placeholder-map -->", "course-map",
     "Bản đồ 16 module trong năm phần."),
]
