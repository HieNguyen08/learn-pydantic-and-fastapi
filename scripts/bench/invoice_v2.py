# invoice_v2.py — model hóa đơn phiên bản 2: đủ tầng 1–3 (Pydantic 2.14)
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, Literal

from pydantic import (AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, GetCoreSchemaHandler,
                      GetJsonSchemaHandler, model_validator)
from pydantic_core import PydanticCustomError, core_schema

WEIGHTS = (31, 29, 23, 19, 17, 13, 7, 5, 3)
RATE = {"0": Decimal(0), "5": Decimal(5), "8": Decimal(8), "10": Decimal(10), "KCT": Decimal(0), "KKKNT": Decimal(0)}


class TaxCode(str):
    """Mã số thuế đã chuẩn hóa và kiểm tra chữ số cuối. Chỉ tạo được qua validate."""

    @classmethod
    def _parse(cls, v: str) -> "TaxCode":
        s = v.replace("-", "").replace(".", "").replace(" ", "")
        if len(s) not in (10, 13) or not s.isdigit():
            raise PydanticCustomError("tax_code_format", "MST phải có 10 hoặc 13 chữ số")
        if s[2:9] == "0000000" or (len(s) == 13 and s[10:] == "000"):
            raise PydanticCustomError("tax_code_format", "MST có thành phần không hợp lệ")
        check = 10 - sum(w * int(c) for w, c in zip(WEIGHTS, s)) % 11
        if str(check) != s[9]:
            raise PydanticCustomError("tax_code_checksum", "MST sai chữ số kiểm tra (cần {expected})",
                                      {"expected": check if check < 10 else "không có"})
        return cls(s)

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        # chuỗi dài 10–17 ký tự (cho phép dấu phân cách) → _parse; serialize lại thành str thường
        return core_schema.no_info_after_validator_function(
            cls._parse, core_schema.str_schema(min_length=10, max_length=17),
            serialization=core_schema.to_string_ser_schema())

    @classmethod
    def __get_pydantic_json_schema__(cls, cs, handler: GetJsonSchemaHandler):
        js = handler(cs)
        js.update(pattern=r"^\d{10}(-?\d{3})?$", description="Mã số thuế 10 hoặc 13 chữ số", examples=["0100233488"])
        return js


def half_up(x: Decimal) -> int:
    return int(x.quantize(Decimal(1), rounding=ROUND_HALF_UP))


VND = Annotated[int, Field(ge=0, le=10**15)]
Qty = Annotated[Decimal, Field(gt=0, le=10**9, max_digits=15, decimal_places=4)]
VatRate = Literal["0", "5", "8", "10", "KCT", "KKKNT"]


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BuyerIn(RequestModel):
    name: Annotated[str, Field(min_length=1, max_length=400)]
    tax_code: TaxCode | None = None
    email: Annotated[str, Field(max_length=254)] | None = None
    address: Annotated[str, Field(max_length=400)] = ""


class LineIn(RequestModel):
    line_no: Annotated[int, Field(ge=1, le=1000)]
    sku: Annotated[str, Field(min_length=1, max_length=50)]
    name: Annotated[str, Field(min_length=1, max_length=500)]
    unit: Annotated[str, Field(min_length=1, max_length=20)]
    quantity: Qty
    unit_price: VND
    vat_rate: VatRate
    amount: VND

    @model_validator(mode="after")
    def _amount(self):
        expected = half_up(self.quantity * self.unit_price)
        if self.amount != expected:
            raise PydanticCustomError("line_amount", "amount phải bằng làm tròn(quantity × unit_price) = {expected}",
                                      {"expected": expected})
        return self

    @property
    def tax(self) -> int:
        return half_up(self.amount * RATE[self.vat_rate] / 100)


def _unique_line_no(lines: list[LineIn]) -> list[LineIn]:
    nos = [l.line_no for l in lines]
    if len(set(nos)) != len(nos):
        raise PydanticCustomError("line_no_duplicate", "line_no bị trùng")
    return lines


class InvoiceIn(RequestModel):
    series: Annotated[str, Field(pattern=r"^[0-9][A-Z0-9]{1,9}$")]
    number: Annotated[int, Field(ge=1, le=99_999_999)]
    seller_tax_code: TaxCode
    buyer: BuyerIn
    issued_at: AwareDatetime
    currency: Literal["VND"] = "VND"
    lines: Annotated[list[LineIn], Field(min_length=1, max_length=1000), AfterValidator(_unique_line_no)]
    total_before_tax: VND
    total_tax: VND
    total: VND

    @model_validator(mode="after")
    def _totals(self):
        before = sum(l.amount for l in self.lines)
        tax = sum(l.tax for l in self.lines)
        errors = []
        if self.total_before_tax != before:
            errors.append(f"total_before_tax phải là {before}")
        if self.total_tax != tax:
            errors.append(f"total_tax phải là {tax}")
        if self.total != self.total_before_tax + self.total_tax:
            errors.append("total phải bằng total_before_tax + total_tax")
        if errors:
            raise PydanticCustomError("invoice_totals", "Tổng tiền không khớp: {detail}", {"detail": "; ".join(errors)})
        return self
