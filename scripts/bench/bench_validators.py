"""Chi phí của validator Python so với ràng buộc trong core, và smart union so với discriminated union (Module 04).

Chạy:  python bench_validators.py → results/validators.json
"""
import json
import random
import statistics
import timeit
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (AfterValidator, BaseModel, BeforeValidator, Discriminator, Field, PlainValidator, Tag,
                      TypeAdapter, WrapValidator, field_validator)

HERE = Path(__file__).parent
N = 1000


def per_item_ns(fn, arg, n_items):
    t = timeit.Timer(lambda: fn(arg))
    k, _ = t.autorange()
    return min(x / k for x in t.repeat(9, k)) / n_items * 1e9


def pos(v):
    if v <= 0:
        raise ValueError("phải > 0")
    return v


def pos_wrap(v, handler):
    v = handler(v)
    if v <= 0:
        raise ValueError("phải > 0")
    return v


def pos_plain(v):
    if type(v) not in (int, float) or v <= 0:
        raise ValueError("phải là số > 0")
    return float(v)


class WithFieldValidator(BaseModel):
    q: float

    @field_validator("q")
    @classmethod
    def _q(cls, v):
        return pos(v)


class WithCore(BaseModel):
    q: Annotated[float, Field(gt=0)]


def bench_constraints():
    data = [random.Random(i).uniform(0.1, 100) for i in range(N)]
    raw = json.dumps(data).encode()
    variants = {
        "không ràng buộc: float": float,
        "Field(gt=0) — trong Rust": Annotated[float, Field(gt=0)],
        "AfterValidator (Python)": Annotated[float, AfterValidator(pos)],
        "BeforeValidator (Python)": Annotated[float, BeforeValidator(pos)],
        "WrapValidator (Python)": Annotated[float, WrapValidator(pos_wrap)],
        "PlainValidator (Python)": Annotated[float, PlainValidator(pos_plain)],
    }
    rows = []
    for name, tp in variants.items():
        ta = TypeAdapter(list[tp])
        rows.append(dict(variant=name, ns_per_item=per_item_ns(ta.validate_json, raw, N)))
    # cùng phép kiểm tra nhưng đặt trong model (mỗi phần tử là một object)
    objs = json.dumps([{"q": q} for q in data]).encode()
    for name, m in (("model + Field(gt=0)", WithCore), ("model + @field_validator", WithFieldValidator)):
        ta = TypeAdapter(list[m])
        rows.append(dict(variant=name, ns_per_item=per_item_ns(ta.validate_json, objs, N)))
    for r in rows:
        print(f"{r['variant']:32s} {r['ns_per_item']:8.1f} ns/phần tử")
    return rows


# ---------------------------------------------------------------- union
class Card(BaseModel):
    method: Literal["card"]
    last4: Annotated[str, Field(pattern=r"^\d{4}$")]
    amount: int


class Transfer(BaseModel):
    method: Literal["transfer"]
    bank_code: str
    ref: str
    amount: int


class Cash(BaseModel):
    method: Literal["cash"]
    amount: int


class EWallet(BaseModel):
    method: Literal["ewallet"]
    provider: Literal["momo", "zalopay", "vnpay"]
    phone: str
    amount: int


class Voucher(BaseModel):
    method: Literal["voucher"]
    code: str
    amount: int


TYPES = (Card, Transfer, Cash, EWallet, Voucher)


def sample(i):
    r = random.Random(i)
    k = i % 5
    return [{"method": "card", "last4": "4242", "amount": r.randint(1, 10**6)},
            {"method": "transfer", "bank_code": "VCB", "ref": f"FT{i}", "amount": r.randint(1, 10**6)},
            {"method": "cash", "amount": r.randint(1, 10**6)},
            {"method": "ewallet", "provider": "momo", "phone": "0901234567", "amount": r.randint(1, 10**6)},
            {"method": "voucher", "code": f"V{i}", "amount": r.randint(1, 10**6)}][k]


def method_of(v):
    return v.get("method") if isinstance(v, dict) else getattr(v, "method", None)


def bench_unions():
    U = Card | Transfer | Cash | EWallet | Voucher
    variants = {
        "smart union (mặc định)": U,
        "left_to_right": Annotated[U, Field(union_mode="left_to_right")],
        "discriminator='method'": Annotated[U, Field(discriminator="method")],
        "Discriminator(callable)": Annotated[
            Annotated[Card, Tag("card")] | Annotated[Transfer, Tag("transfer")] | Annotated[Cash, Tag("cash")]
            | Annotated[EWallet, Tag("ewallet")] | Annotated[Voucher, Tag("voucher")], Discriminator(method_of)],
    }
    ok = json.dumps([sample(i) for i in range(N)]).encode()
    bad_one = [sample(i) for i in range(5)]
    bad_one[3] = {"method": "ewallet", "provider": "paypal", "phone": "0901", "amount": 1}
    rows = []
    for name, tp in variants.items():
        ta = TypeAdapter(list[tp])
        ns = per_item_ns(ta.validate_json, ok, N)
        try:
            ta.validate_python(bad_one)
            n_err = 0
        except Exception as e:
            n_err = e.error_count()
        rows.append(dict(variant=name, ns_per_item=ns, errors_for_one_bad_item=n_err))
        print(f"{name:28s} {ns:8.1f} ns/phần tử  lỗi báo cho 1 phần tử sai: {n_err}")
    # theo số thành viên của union
    scaling = []
    for k in range(1, 6):
        members = TYPES[:k]
        Uk = members[0] if k == 1 else __import__("functools").reduce(lambda a, b: a | b, members)
        data = json.dumps([sample(i * 5 + (k - 1)) for i in range(N)]).encode()   # luôn là thành viên CUỐI
        for name, tp in (("smart", Uk), ("discriminated", Annotated[Uk, Field(discriminator="method")] if k > 1 else Uk)):
            ns = per_item_ns(TypeAdapter(list[tp]).validate_json, data, N)
            scaling.append(dict(members=k, variant=name, ns_per_item=ns))
            print(f"  k={k} {name:13s} {ns:8.1f} ns")
    return rows, scaling


def main():
    out = {"constraints": bench_constraints()}
    out["unions"], out["union_scaling"] = bench_unions()
    (HERE / "results" / "validators.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
