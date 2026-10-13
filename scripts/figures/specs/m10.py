MD = "docs/10-database-va-persistence.md"
MODULE = "10"
PREFIX = "10"

FIGS = [
    ("<!-- placeholder-layers -->", "layers",
     "Ba biểu diễn của một hóa đơn: schema vào (Pydantic), model bảng (ORM), schema ra (Pydantic, from_attributes)."),
    ("<!-- placeholder-session -->", "session",
     "Session-per-request: transaction mở khi mượn kết nối và commit trước khi gửi 201 nhờ scope=\"function\"."),
    ("<!-- placeholder-pool -->", "pool",
     "Pool kết nối: request chờ mượn theo FIFO, quá pool_timeout thì lỗi; commit trả kết nối về pool."),
    ("<!-- placeholder-little -->", "little",
     "Erlang C với thời gian giữ kết nối đo được: xác suất request phải chờ pool theo tải và kích thước pool."),
    ("<!-- placeholder-pool-size -->", "pool-size",
     "Số đo thật: thông lượng đạt đỉnh ở pool = 2 × số core; thêm kết nối chỉ chuyển hàng đợi từ app vào DB."),
    ("<!-- placeholder-nplus1 -->", "nplus1",
     "Số đo thật: N+1 tăng tuyến tính theo số round trip; selectinload và joinedload giữ số truy vấn cố định."),
    ("<!-- placeholder-numbering -->", "numbering",
     "Số đo thật: ba cách cấp số hóa đơn dưới 32 giao dịch đồng thời — đúng đắn và thông lượng."),
    ("<!-- placeholder-idem -->", "idem",
     "Idempotency key: kiểm tra-rồi-ghi để lọt race, giành khóa trước bằng ON CONFLICT thì không; kết cục đo được của 50 request trùng."),
    ("<!-- placeholder-rls -->", "rls",
     "Row-Level Security: cùng một truy vấn không WHERE, mỗi tenant chỉ thấy hàng của mình."),
    ("<!-- placeholder-lockqueue -->", "lockqueue",
     "Số đo thật: ALTER TABLE chờ khóa sau transaction dài chặn mọi SELECT đến sau nó; lock_timeout loại bỏ hoàn toàn hiện tượng này."),
    ("<!-- placeholder-expand -->", "expand",
     "Expand/contract: đổi tên cột qua sáu bước, mỗi bước tương thích với phiên bản app liền kề."),
    ("<!-- placeholder-outbox -->", "outbox",
     "Dual write so với transactional outbox."),
    ("<!-- placeholder-outbox-scale -->", "outbox-scale",
     "Số đo thật: relay outbox chỉ mở rộng theo số relay khi dùng SKIP LOCKED."),
]
