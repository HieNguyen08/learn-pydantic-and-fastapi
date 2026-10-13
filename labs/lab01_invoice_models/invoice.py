"""Lab 01 — Mô hình hóa hóa đơn bằng Pydantic (lời giải tham khảo).

Chạy:  pytest -q            (trong thư mục này)
       python invoice.py    (in ví dụ lỗi)
"""
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

WEIGHTS = (31, 29, 23, 19, 17, 13, 7, 5, 3)
RATE = {"0": 0, "5": 5, "8": 8, "10": 10, "KCT": 0, "KKKNT": 0}


# ---------------------------------------------------------------- Bước 1: kiểu MST
def check_tax_code(v: str) -> str:
    s = v.replace("-", "").replace(" ", "")
    if len(s) not in (10, 13) or not s.isdigit():
        raise PydanticCustomError("tax_code_format", "MST phải có 10 hoặc 13 chữ số")
    if s[2:9] == "0000000" or (len(s) == 13 and s[10:] == "000"):
        raise PydanticCustomError("tax_code_format", "MST có thành phần không hợp lệ")
    check = 10 - sum(w * int(c) for w, c in zip(WEIGHTS, s)) % 11
    if check == 10 or int(s[9]) != check:
        raise PydanticCustomError("tax_code_checksum", "MST sai chữ số kiểm tra")
    return s


TaxCode = Annotated[str, Field(min_length=10, max_length=17), AfterValidator(check_tax_code)]
VND = Annotated[int, Field(ge=0, le=10**15, strict=True)]          # tiền: số nguyên, không nhận "1000" hay 1000.0


# ---------------------------------------------------------------- Bước 2: làm tròn
def half_up(x: Decimal) -> int:
    return int(x.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def line_tax(amount: int, rate: str) -> int:
    return half_up(Decimal(amount) * RATE[rate] / 100)


# ---------------------------------------------------------------- Bước 3: model
class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Buyer(Strict):
    name: Annotated[str, Field(min_length=1, max_length=400)]
    tax_code: TaxCode | None = None


class Line(Strict):
    name: Annotated[str, Field(min_length=1, max_length=500)]
    quantity: Annotated[Decimal, Field(gt=0, max_digits=15, decimal_places=4)]
    unit_price: VND
    vat_rate: Literal["0", "5", "8", "10", "KCT", "KKKNT"]
    amount: VND

    @model_validator(mode="after")
    def _amount(self):
        expected = half_up(self.quantity * self.unit_price)
        if self.amount != expected:
            raise PydanticCustomError("line_amount", "amount phải bằng {expected}", {"expected": expected})
        return self


class Invoice(Strict):
    seller_tax_code: TaxCode
    buyer: Buyer
    issued_at: AwareDatetime
    lines: Annotated[list[Line], Field(min_length=1, max_length=1000)]
    total_before_tax: VND
    total_tax: VND
    total: VND

    @model_validator(mode="after")
    def _totals(self):
        before = sum(l.amount for l in self.lines)
        tax = sum(line_tax(l.amount, l.vat_rate) for l in self.lines)
        if (self.total_before_tax, self.total_tax, self.total) != (before, tax, before + tax):
            raise PydanticCustomError("invoice_totals", "tổng không khớp: cần {b} + {t} = {s}",
                                      {"b": before, "t": tax, "s": before + tax})
        return self


if __name__ == "__main__":
    from pydantic import ValidationError
    bad = {"seller_tax_code": "0100109107", "buyer": {"name": "  "}, "issued_at": "2026-10-13T09:00:00",
           "lines": [{"name": "Cà phê", "quantity": "2", "unit_price": "29000", "vat_rate": "8%", "amount": 58000}],
           "total_before_tax": 58000, "total_tax": 4640, "total": 62640}
    try:
        Invoice.model_validate(bad)
    except ValidationError as e:
        for err in e.errors():
            print(f"{'.'.join(map(str, err['loc'])):28s} {err['type']:22s} {err['msg']}")
