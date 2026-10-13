"""Cùng một đặc tả hóa đơn, cài bằng nhiều thư viện để so sánh công bằng.

Hai mức kiểm tra:
  - "schema": kiểu + ràng buộc từng trường (độ dài, khoảng giá trị, enum, regex MST).
  - "full":   schema + quy tắc nghiệp vụ viết bằng Python (checksum MST, amount từng dòng,
              tổng trước thuế, tổng thuế, tổng cộng).
Mỗi hàm factory trả về `decode(raw: bytes) -> object`, ném lỗi nếu dữ liệu sai.
"""
import json
from datetime import datetime

from payload import RATE_PCT, mst_is_valid

MST_RE = r"^\d{10}(\d{3})?$"
RATES = ("0", "5", "8", "10", "KCT", "KKKNT")


def check_business(seller_mst, lines, before, tax, total):
    """Quy tắc nghiệp vụ dùng chung (thuần Python) — `lines` là iterable (qty, price, rate, amount)."""
    if not mst_is_valid(seller_mst):
        raise ValueError("MST người bán sai chữ số kiểm tra")
    s_before = s_tax = 0
    for qty, price, rate, amount in lines:
        if amount != round(qty * price):
            raise ValueError("amount != quantity * unit_price")
        s_before += amount
        s_tax += round(amount * RATE_PCT[rate] / 100)
    if s_before != before or s_tax != tax or before + tax != total:
        raise ValueError("tổng tiền không khớp")


# ----------------------------------------------------------------------------- baseline
def make_json_loads(level):
    return json.loads


def make_orjson_loads(level):
    import orjson
    return orjson.loads


# ----------------------------------------------------------------------------- Pydantic v2
def _pydantic_v2_models(level):
    from typing import Annotated, Literal, Optional

    from pydantic import BaseModel, Field, field_validator, model_validator

    class Buyer(BaseModel):
        name: Annotated[str, Field(min_length=1, max_length=400)]
        tax_code: Optional[Annotated[str, Field(pattern=MST_RE)]] = None
        email: Optional[Annotated[str, Field(max_length=254)]] = None
        address: Annotated[str, Field(max_length=400)]

    class Line(BaseModel):
        line_no: Annotated[int, Field(ge=1)]
        sku: Annotated[str, Field(min_length=1, max_length=50)]
        name: Annotated[str, Field(min_length=1, max_length=500)]
        unit: Annotated[str, Field(min_length=1, max_length=20)]
        quantity: Annotated[float, Field(gt=0)]
        unit_price: Annotated[int, Field(ge=0)]
        vat_rate: Literal["0", "5", "8", "10", "KCT", "KKKNT"]
        amount: Annotated[int, Field(ge=0)]

    class Invoice(BaseModel):
        series: Annotated[str, Field(min_length=1, max_length=10)]
        number: Annotated[int, Field(ge=1, le=99_999_999)]
        seller_tax_code: Annotated[str, Field(pattern=MST_RE)]
        buyer: Buyer
        issued_at: datetime
        currency: Literal["VND"]
        lines: Annotated[list[Line], Field(min_length=1, max_length=1000)]
        total_before_tax: Annotated[int, Field(ge=0)]
        total_tax: Annotated[int, Field(ge=0)]
        total: Annotated[int, Field(ge=0)]

    if level == "schema":
        return Invoice

    class InvoiceFull(Invoice):
        @field_validator("seller_tax_code")
        @classmethod
        def _mst(cls, v):  # checksum được gọi trong check_business
            return v

        @model_validator(mode="after")
        def _totals(self):
            check_business(self.seller_tax_code,
                           ((l.quantity, l.unit_price, l.vat_rate, l.amount) for l in self.lines),
                           self.total_before_tax, self.total_tax, self.total)
            return self

    return InvoiceFull


def make_pydantic_v2_json(level):
    """Đường nhanh: bytes JSON → model, parse JSON bằng jiter (Rust)."""
    return _pydantic_v2_models(level).model_validate_json


def make_pydantic_v2_dict(level):
    """Đường phổ biến nhưng chậm hơn: json.loads (C) → dict → model_validate."""
    m = _pydantic_v2_models(level)
    return lambda raw: m.model_validate(json.loads(raw))


def make_pydantic_v2_strict(level):
    m = _pydantic_v2_models(level)
    return lambda raw: m.model_validate_json(raw, strict=True)


def make_pydantic_v2_typeadapter_rebuilt(level):
    """Anti-pattern: tạo TypeAdapter mới trong mỗi request."""
    from pydantic import TypeAdapter
    m = _pydantic_v2_models(level)
    # TypeAdapter cho một kiểu không phải BaseModel (list[Invoice]) phải dựng core schema mới
    return lambda raw: TypeAdapter(list[m]).validate_json(b"[" + raw + b"]")[0]


# ----------------------------------------------------------------------------- Pydantic v1
def _pydantic_v1_models(level):
    from typing import List, Literal, Optional

    from pydantic import BaseModel, confloat, conint, constr, root_validator

    class Buyer(BaseModel):
        name: constr(min_length=1, max_length=400)
        tax_code: Optional[constr(regex=MST_RE)] = None
        email: Optional[constr(max_length=254)] = None
        address: constr(max_length=400)

    class Line(BaseModel):
        line_no: conint(ge=1)
        sku: constr(min_length=1, max_length=50)
        name: constr(min_length=1, max_length=500)
        unit: constr(min_length=1, max_length=20)
        quantity: confloat(gt=0)
        unit_price: conint(ge=0)
        vat_rate: Literal["0", "5", "8", "10", "KCT", "KKKNT"]
        amount: conint(ge=0)

    class Invoice(BaseModel):
        series: constr(min_length=1, max_length=10)
        number: conint(ge=1, le=99_999_999)
        seller_tax_code: constr(regex=MST_RE)
        buyer: Buyer
        issued_at: datetime
        currency: Literal["VND"]
        lines: List[Line]
        total_before_tax: conint(ge=0)
        total_tax: conint(ge=0)
        total: conint(ge=0)

    if level == "schema":
        return Invoice

    class InvoiceFull(Invoice):
        @root_validator(skip_on_failure=True)
        def _totals(cls, values):
            check_business(values["seller_tax_code"],
                           ((l.quantity, l.unit_price, l.vat_rate, l.amount) for l in values["lines"]),
                           values["total_before_tax"], values["total_tax"], values["total"])
            return values

    return InvoiceFull


def make_pydantic_v1(level):
    return _pydantic_v1_models(level).parse_raw


# ----------------------------------------------------------------------------- msgspec
def make_msgspec(level):
    from typing import Annotated, Literal, Optional, Union

    import msgspec
    from msgspec import Meta, Struct

    class Buyer(Struct):
        name: Annotated[str, Meta(min_length=1, max_length=400)]
        address: Annotated[str, Meta(max_length=400)]
        tax_code: Optional[Annotated[str, Meta(pattern=MST_RE)]] = None
        email: Optional[Annotated[str, Meta(max_length=254)]] = None

    class Line(Struct):
        line_no: Annotated[int, Meta(ge=1)]
        sku: Annotated[str, Meta(min_length=1, max_length=50)]
        name: Annotated[str, Meta(min_length=1, max_length=500)]
        unit: Annotated[str, Meta(min_length=1, max_length=20)]
        quantity: Annotated[float, Meta(gt=0)]
        unit_price: Annotated[int, Meta(ge=0)]
        vat_rate: Literal["0", "5", "8", "10", "KCT", "KKKNT"]
        amount: Annotated[int, Meta(ge=0)]

    class Invoice(Struct):
        series: Annotated[str, Meta(min_length=1, max_length=10)]
        number: Annotated[int, Meta(ge=1, le=99_999_999)]
        seller_tax_code: Annotated[str, Meta(pattern=MST_RE)]
        buyer: Buyer
        issued_at: datetime
        currency: Literal["VND"]
        lines: Annotated[list[Line], Meta(min_length=1, max_length=1000)]
        total_before_tax: Annotated[int, Meta(ge=0)]
        total_tax: Annotated[int, Meta(ge=0)]
        total: Annotated[int, Meta(ge=0)]

    class InvoiceFull(Invoice):
        def __post_init__(self):  # msgspec gọi sau khi decode xong
            check_business(self.seller_tax_code,
                           ((l.quantity, l.unit_price, l.vat_rate, l.amount) for l in self.lines),
                           self.total_before_tax, self.total_tax, self.total)

    dec = msgspec.json.Decoder(InvoiceFull if level == "full" else Invoice)
    return dec.decode


# ----------------------------------------------------------------------------- dataclasses tự viết
def make_dataclass_manual(level):
    import re
    from dataclasses import dataclass

    mst_re = re.compile(MST_RE)

    @dataclass(slots=True)
    class Line:
        line_no: int; sku: str; name: str; unit: str
        quantity: float; unit_price: int; vat_rate: str; amount: int

    @dataclass(slots=True)
    class Invoice:
        series: str; number: int; seller_tax_code: str; buyer: dict; issued_at: datetime
        currency: str; lines: list; total_before_tax: int; total_tax: int; total: int

    def need(cond, msg):
        if not cond:
            raise ValueError(msg)

    def s(d, k, lo, hi):
        v = d[k]
        need(type(v) is str and lo <= len(v) <= hi, k)
        return v

    def i(d, k, lo, hi=None):
        v = d[k]
        need(type(v) is int and v >= lo and (hi is None or v <= hi), k)
        return v

    def decode(raw):
        d = json.loads(raw)
        lines = []
        need(type(d["lines"]) is list and 1 <= len(d["lines"]) <= 1000, "lines")
        for x in d["lines"]:
            q = x["quantity"]
            need(type(q) in (int, float) and q > 0, "quantity")
            need(x["vat_rate"] in RATES, "vat_rate")
            lines.append(Line(i(x, "line_no", 1), s(x, "sku", 1, 50), s(x, "name", 1, 500),
                              s(x, "unit", 1, 20), q, i(x, "unit_price", 0), x["vat_rate"],
                              i(x, "amount", 0)))
        b = d["buyer"]
        s(b, "name", 1, 400); s(b, "address", 0, 400)
        if b.get("tax_code") is not None:
            need(mst_re.match(b["tax_code"]), "buyer.tax_code")
        mst = d["seller_tax_code"]
        need(type(mst) is str and mst_re.match(mst), "seller_tax_code")
        need(d["currency"] == "VND", "currency")
        inv = Invoice(s(d, "series", 1, 10), i(d, "number", 1, 99_999_999), mst, b,
                      datetime.fromisoformat(d["issued_at"]), "VND", lines,
                      i(d, "total_before_tax", 0), i(d, "total_tax", 0), i(d, "total", 0))
        if level == "full":
            check_business(mst, ((l.quantity, l.unit_price, l.vat_rate, l.amount) for l in lines),
                           inv.total_before_tax, inv.total_tax, inv.total)
        return inv

    return decode


# ----------------------------------------------------------------------------- marshmallow
def make_marshmallow(level):
    from marshmallow import Schema, ValidationError, fields, post_load, validate, validates_schema

    class BuyerS(Schema):
        name = fields.String(required=True, validate=validate.Length(1, 400))
        tax_code = fields.String(allow_none=True, load_default=None, validate=validate.Regexp(MST_RE))
        email = fields.String(allow_none=True, load_default=None, validate=validate.Length(max=254))
        address = fields.String(required=True, validate=validate.Length(max=400))

    class LineS(Schema):
        line_no = fields.Integer(required=True, strict=True, validate=validate.Range(min=1))
        sku = fields.String(required=True, validate=validate.Length(1, 50))
        name = fields.String(required=True, validate=validate.Length(1, 500))
        unit = fields.String(required=True, validate=validate.Length(1, 20))
        quantity = fields.Float(required=True, validate=validate.Range(min=0, min_inclusive=False))
        unit_price = fields.Integer(required=True, strict=True, validate=validate.Range(min=0))
        vat_rate = fields.String(required=True, validate=validate.OneOf(RATES))
        amount = fields.Integer(required=True, strict=True, validate=validate.Range(min=0))

    class InvoiceS(Schema):
        series = fields.String(required=True, validate=validate.Length(1, 10))
        number = fields.Integer(required=True, strict=True, validate=validate.Range(1, 99_999_999))
        seller_tax_code = fields.String(required=True, validate=validate.Regexp(MST_RE))
        buyer = fields.Nested(BuyerS, required=True)
        issued_at = fields.AwareDateTime(required=True)
        currency = fields.String(required=True, validate=validate.Equal("VND"))
        lines = fields.List(fields.Nested(LineS), required=True, validate=validate.Length(1, 1000))
        total_before_tax = fields.Integer(required=True, strict=True, validate=validate.Range(min=0))
        total_tax = fields.Integer(required=True, strict=True, validate=validate.Range(min=0))
        total = fields.Integer(required=True, strict=True, validate=validate.Range(min=0))

        @validates_schema
        def _totals(self, d, **kw):
            if level == "full":
                try:
                    check_business(d["seller_tax_code"],
                                   ((l["quantity"], l["unit_price"], l["vat_rate"], l["amount"]) for l in d["lines"]),
                                   d["total_before_tax"], d["total_tax"], d["total"])
                except ValueError as e:
                    raise ValidationError(str(e))

    sch = InvoiceS()
    return lambda raw: sch.loads(raw)


# ----------------------------------------------------------------------------- attrs + cattrs
def make_attrs_cattrs(level):
    import re
    from typing import Optional

    import attrs
    import cattrs
    from attrs import validators as v

    mst_re = re.compile(MST_RE)

    def length(lo, hi):
        def _f(inst, att, val):
            if not (lo <= len(val) <= hi):
                raise ValueError(att.name)
        return _f

    @attrs.define
    class Buyer:
        name: str = attrs.field(validator=length(1, 400))
        address: str = attrs.field(validator=length(0, 400))
        tax_code: Optional[str] = attrs.field(default=None, validator=v.optional(v.matches_re(mst_re)))
        email: Optional[str] = None

    @attrs.define
    class Line:
        line_no: int = attrs.field(validator=v.ge(1))
        sku: str = attrs.field(validator=length(1, 50))
        name: str = attrs.field(validator=length(1, 500))
        unit: str = attrs.field(validator=length(1, 20))
        quantity: float = attrs.field(validator=v.gt(0))
        unit_price: int = attrs.field(validator=v.ge(0))
        vat_rate: str = attrs.field(validator=v.in_(RATES))
        amount: int = attrs.field(validator=v.ge(0))

    @attrs.define
    class Invoice:
        series: str = attrs.field(validator=length(1, 10))
        number: int = attrs.field(validator=[v.ge(1), v.le(99_999_999)])
        seller_tax_code: str = attrs.field(validator=v.matches_re(mst_re))
        buyer: Buyer
        issued_at: datetime
        currency: str = attrs.field(validator=v.in_(("VND",)))
        lines: list[Line] = attrs.field(validator=v.min_len(1))
        total_before_tax: int = attrs.field(validator=v.ge(0))
        total_tax: int = attrs.field(validator=v.ge(0))
        total: int = attrs.field(validator=v.ge(0))

        def __attrs_post_init__(self):
            if level == "full":
                check_business(self.seller_tax_code,
                               ((l.quantity, l.unit_price, l.vat_rate, l.amount) for l in self.lines),
                               self.total_before_tax, self.total_tax, self.total)

    conv = cattrs.Converter()
    conv.register_structure_hook(datetime, lambda x, _: datetime.fromisoformat(x))
    return lambda raw: conv.structure(json.loads(raw), Invoice)


IMPLS = {
    "json.loads (chỉ parse)": make_json_loads,
    "orjson.loads (chỉ parse)": make_orjson_loads,
    "pydantic v2 · model_validate_json": make_pydantic_v2_json,
    "pydantic v2 · json.loads + model_validate": make_pydantic_v2_dict,
    "pydantic v2 · strict": make_pydantic_v2_strict,
    "pydantic v2 · TypeAdapter mỗi request": make_pydantic_v2_typeadapter_rebuilt,
    "pydantic v1 · parse_raw": make_pydantic_v1,
    "msgspec · Struct": make_msgspec,
    "dataclasses + code tay": make_dataclass_manual,
    "marshmallow 4": make_marshmallow,
    "attrs + cattrs": make_attrs_cattrs,
}
