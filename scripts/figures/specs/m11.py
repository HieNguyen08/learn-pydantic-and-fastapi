MD = "docs/11-bao-mat-api.md"
MODULE = "11"
PREFIX = "11"

FIGS = [
    ("<!-- placeholder-threat -->", "threat",
     "Sơ đồ luồng dữ liệu của Mekong Cloud với các ranh giới tin cậy và đe dọa STRIDE tương ứng."),
    ("<!-- placeholder-owasp -->", "owasp",
     "OWASP API Security Top 10 (2023) và cơ chế chặn từng rủi ro trong khóa học."),
    ("<!-- placeholder-oauth -->", "oauth",
     "Hai luồng OAuth: client credentials cho máy POS, authorization code + PKCE cho nhân viên qua trình duyệt."),
    ("<!-- placeholder-jwt -->", "jwt",
     "Cấu trúc JWT và bốn bước kiểm tra bắt buộc ở resource server."),
    ("<!-- placeholder-jwt-attacks -->", "jwt-attacks",
     "Số đo thật: năm token tấn công qua decoder tự viết và PyJWT dùng đúng cách."),
    ("<!-- placeholder-jwt-cost -->", "jwt-cost",
     "Số đo thật: chi phí ký và kiểm JWT theo thuật toán."),
    ("<!-- placeholder-hash -->", "hash",
     "Số đo thật: chi phí một lần băm theo hàm; và ước lượng thời gian phá mật khẩu 8 ký tự."),
    ("<!-- placeholder-bola -->", "bola",
     "BOLA: truy vấn không gắn tenant làm lộ hóa đơn; gắn tenant từ principal trả 404."),
    ("<!-- placeholder-bopla -->", "bopla",
     "Số đo thật: cùng một body PATCH độc hại qua ba cách xử lý."),
    ("<!-- placeholder-ratelimit -->", "ratelimit",
     "Mô phỏng: cửa sổ cố định để lọt gấp đôi giới hạn quanh ranh giới, GCRA thì không."),
    ("<!-- placeholder-payload -->", "payload",
     "Số đo thật: chi phí từ chối tăng theo kích thước input; giới hạn body trả 413 gần như miễn phí."),
    ("<!-- placeholder-ssrf -->", "ssrf",
     "Quy trình chặn SSRF cho URL webhook: chuẩn hóa, phân giải, kiểm từng địa chỉ, kết nối đúng IP."),
]
