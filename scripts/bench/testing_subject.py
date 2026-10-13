"""Mã "cần kiểm thử" cho thí nghiệm Module 12: bản đúng và các bản có lỗi cài sẵn (giống lỗi thật hay gặp)."""
from datetime import datetime, timezone
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal  # noqa: F401 (HALF_EVEN cho đột biến)

from pydantic import BaseModel, field_serializer

WEIGHTS = (31, 29, 23, 19, 17, 13, 7, 5, 3)


# ---------------------------------------------------------------- MST
def mst_is_valid(s: str) -> bool:
    """MST 10 số (doanh nghiệp) hoặc 13 số (chi nhánh, 3 số cuối 001–999).
    Chữ số thứ 10 = 10 - (Σ w·d mod 11); kết quả 10 → tiền tố không hợp lệ; 7 số giữa không được toàn 0."""
    if len(s) not in (10, 13) or not s.isdigit():
        return False
    if s[2:9] == "0000000" or (len(s) == 13 and s[10:] == "000"):
        return False
    check = 10 - sum(w * int(c) for w, c in zip(WEIGHTS, s[:9])) % 11
    return check < 10 and int(s[9]) == check


def invoice_totals(lines: list[tuple[int, int]]) -> tuple[int, int, int]:
    """(tiền trước thuế, tiền thuế, tổng) — thuế làm tròn theo TỪNG dòng rồi cộng (quy tắc của Mekong Cloud)."""
    before = sum(amount for amount, _ in lines)
    tax = sum(line_tax(amount, rate) for amount, rate in lines)
    return before, tax, before + tax


def mst_is_valid_buggy(s: str) -> bool:
    """Lỗi: so ký tự cuối của chuỗi check ("10"[-1] == "0") → chấp nhận MST có tiền tố không hợp lệ."""
    if len(s) not in (10, 13) or not s.isdigit():
        return False
    if s[2:9] == "0000000" or (len(s) == 13 and s[10:] == "000"):
        return False
    check = str(10 - sum(w * int(c) for w, c in zip(WEIGHTS, s[:9])) % 11)
    return s[9] == check[-1]


# ---------------------------------------------------------------- thuế một dòng
def line_tax(amount: int, rate_pct: int) -> int:
    """Bản đúng: làm tròn nửa lên (half-up) tới đồng."""
    return int((Decimal(amount) * rate_pct / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def line_tax_buggy(amount: int, rate_pct: int) -> int:
    """Lỗi: round() của Python làm tròn kiểu ngân hàng (half-even) và qua float."""
    return round(amount * rate_pct / 100)


# ---------------------------------------------------------------- round-trip model
class EventOut(BaseModel):
    ticket_id: int
    created_at: datetime


class EventOutBuggy(BaseModel):
    ticket_id: int
    created_at: datetime

    @field_serializer("created_at")
    def _fmt(self, v: datetime) -> str:            # lỗi: định dạng tay, đánh rơi múi giờ và micro giây
        return v.strftime("%Y-%m-%dT%H:%M:%S")


UTC = timezone.utc
