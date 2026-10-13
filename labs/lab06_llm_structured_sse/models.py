"""Model của Lab 06: bản nháp hóa đơn do LLM trích xuất (giống Module 15)."""
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

WEIGHTS = (31, 29, 23, 19, 17, 13, 7, 5, 3)


def mst_ok(s: str) -> bool:
    c = 10 - sum(w * int(x) for w, x in zip(WEIGHTS, s[:9])) % 11
    return len(s) == 10 and s.isdigit() and c < 10 and int(s[9]) == c


class ExtractedLine(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    quantity: Annotated[int, Field(ge=1, le=1000)]
    unit_price: Annotated[int, Field(ge=0, le=100_000_000)]


class InvoiceDraft(BaseModel):
    buyer_name: Annotated[str, Field(min_length=1, max_length=120)]
    buyer_tax_code: Annotated[str, Field(pattern=r"^[0-9]{10}$")]
    vat_rate: Literal["0", "5", "8", "10"]
    lines: Annotated[list[ExtractedLine], Field(min_length=1, max_length=5)]

    @field_validator("buyer_tax_code")
    @classmethod
    def _checksum(cls, v: str) -> str:
        if not mst_ok(v):
            raise ValueError("MST sai chữ số kiểm tra")
        return v


class LinePreview(BaseModel):
    name: str | None = None
    quantity: int | None = None
    unit_price: int | None = None


class DraftPreview(BaseModel):
    """Bản xem trước khi stream: mọi trường tùy chọn."""
    buyer_name: str | None = None
    buyer_tax_code: str | None = None
    vat_rate: str | None = None
    lines: list[LinePreview] = []
