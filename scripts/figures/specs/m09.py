MD = "docs/09-async-dong-thoi-hieu-nang.md"
MODULE = "09"
PREFIX = "9"

FIGS = [
    ("<!-- placeholder-e1 -->", "e1",
     "Số đo thật (e1): throughput và latency theo số kết nối đồng thời của ba cách chờ I/O 50 ms; đường chấm là trần tính bằng định luật Little."),
    ("<!-- placeholder-e2 -->", "e2",
     "Số đo thật (e2): latency của /health dưới ba loại tải nền."),
    ("<!-- placeholder-e6 -->", "e6",
     "Số đo thật (e6): nới giới hạn threadpool từ 40 lên 100 luồng dịch trần throughput đúng như Little dự đoán."),
    ("<!-- placeholder-e4 -->", "e4",
     "Số đo thật (e4, open-loop): latency trung bình, p50, p99 theo utilization."),
    ("<!-- placeholder-theory -->", "theory",
     "Đối chiếu số đo e4 với lý thuyết hàng đợi: trung bình so với M/D/1 và M/M/1 (trái); p99 so với mô phỏng M/D/1 (phải)."),
    ("<!-- placeholder-nagle -->", "nagle",
     "Số đo thật: thêm worker làm chậm đi do Nagle + delayed ACK (e3); chỉ tổ hợp vòng lặp asyncio với --workers bị ảnh hưởng (e9)."),
    ("<!-- placeholder-usl -->", "usl",
     "Universal Scalability Law khớp với throughput theo số worker sau khi đã sửa TCP_NODELAY."),
    ("<!-- placeholder-capacity -->", "capacity",
     "Kế hoạch năng lực của hai dịch vụ, tính bằng định luật Little và mục tiêu utilization."),
]
