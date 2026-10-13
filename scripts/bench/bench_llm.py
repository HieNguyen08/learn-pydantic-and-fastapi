"""Thí nghiệm cho Module 15 — Pydantic cho LLM (chạy trên CPU) → results/llm.json

Model: Qwen/Qwen2.5-0.5B-Instruct (transformers, greedy). Ràng buộc đầu ra: xgrammar.

  l1  trích xuất hóa đơn từ văn bản: prompt thuần / JSON mode (ngữ pháp JSON bất kỳ) / ràng buộc theo JSON Schema
      của model Pydantic → tỉ lệ parse được, hợp lệ Pydantic, đúng ngữ nghĩa; số token; thời gian
  l2  vòng validate–retry cho prompt thuần: gửi lại lỗi Pydantic cho model, tối đa 2 lần
  l3  chi phí ràng buộc: biên dịch grammar, thời gian sinh mỗi token có/không có mask
  l4  partial JSON khi streaming: validate tiền tố bằng experimental_allow_partial; chi phí validate lại mỗi token
Chạy:  python bench_llm.py [--only l1 l2] [--n 30]
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

HERE = Path(__file__).parent
OUT = HERE / "results" / "llm.json"
sys.path.insert(0, str(HERE))
MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
WEIGHTS = (31, 29, 23, 19, 17, 13, 7, 5, 3)


def mst_ok(s: str) -> bool:
    c = 10 - sum(w * int(x) for w, x in zip(WEIGHTS, s[:9])) % 11
    return len(s) == 10 and s.isdigit() and c < 10 and int(s[9]) == c


class ExtractedLine(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    quantity: Annotated[int, Field(ge=1, le=1000)]
    unit_price: Annotated[int, Field(ge=0, le=100_000_000)]


class InvoiceDraft(BaseModel):
    """Bản nháp hóa đơn do LLM trích từ tin nhắn của khách."""
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
    """Bản xem trước khi streaming: mọi trường tùy chọn, không kiểm ràng buộc nghiệp vụ."""
    name: str | None = None
    quantity: int | None = None
    unit_price: int | None = None


class DraftPreview(BaseModel):
    buyer_name: str | None = None
    buyer_tax_code: str | None = None
    vat_rate: str | None = None
    lines: list[LinePreview] = []


ITEMS = [("cà phê sữa đá", 29000), ("bánh mì thịt", 25000), ("giấy in nhiệt 80mm", 15000), ("trà đào", 35000),
         ("máy quét mã vạch", 1250000), ("phí triển khai", 3000000), ("nước suối", 8000), ("bánh flan", 12000)]
BUYERS = ["Công ty TNHH Sông Hậu", "Cửa hàng Minh Anh", "Công ty CP Cà Phê Phố Núi", "Siêu thị Mini Bảo Châu",
          "Công ty TNHH Một Thành Viên Gạo Ngon", "Nhà hàng Gió Bấc", "Tiệm bánh Hoa Sữa", "Công ty CP Thiết Bị Ánh Dương"]


def make_mst(rng):
    while True:
        f = "".join(str(rng.randint(0, 9)) for _ in range(9))
        c = 10 - sum(w * int(x) for w, x in zip(WEIGHTS, f)) % 11
        if c < 10 and f[2:9] != "0000000":
            return f + str(c)


def make_case(i):
    rng = random.Random(1000 + i)
    buyer = rng.choice(BUYERS)
    mst = make_mst(rng)
    rate = rng.choice(["0", "5", "8", "10"])
    lines = [(n, rng.choice([1, 2, 3, 5, 10]), p) for n, p in rng.sample(ITEMS, rng.randint(1, 3))]
    parts = ", ".join(f"{q} {n} giá {p:,} đồng".replace(",", ".") for n, q, p in lines)
    text = rng.choice([
        f"Xuất hóa đơn cho {buyer}, MST {mst}, thuế GTGT {rate}%: {parts}.",
        f"Chào shop, bên mình là {buyer} (mã số thuế {mst}). Lấy giúp {parts}. Thuế suất {rate}% nhé.",
        f"{buyer} – MST: {mst}. Đơn hàng: {parts}. VAT {rate}%.",
    ])
    gold = dict(buyer_name=buyer, buyer_tax_code=mst, vat_rate=rate,
                lines=[dict(name=n, quantity=q, unit_price=p) for n, q, p in lines])
    return text, gold


SYSTEM = ("Bạn trích xuất thông tin hóa đơn từ tin nhắn của khách hàng. Chỉ trả về MỘT đối tượng JSON, không giải thích, "
          "theo đúng JSON Schema sau:\n")


def semantic_ok(d: InvoiceDraft, gold: dict) -> dict:
    total = sum(l.quantity * l.unit_price for l in d.lines)
    gtotal = sum(l["quantity"] * l["unit_price"] for l in gold["lines"])
    return dict(buyer=d.buyer_name.strip().lower() == gold["buyer_name"].lower(), mst=d.buyer_tax_code == gold["buyer_tax_code"],
                rate=d.vat_rate == gold["vat_rate"], total=total == gtotal)


class LLM:
    def __init__(self):
        import torch
        import xgrammar as xgr
        from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer
        torch.set_num_threads(4)
        self.torch, self.xgr = torch, xgr
        self.tok = AutoTokenizer.from_pretrained(MODEL)
        self.model = AutoModelForCausalLM.from_pretrained(MODEL)
        cfg = AutoConfig.from_pretrained(MODEL)
        self.info = xgr.TokenizerInfo.from_huggingface(self.tok, vocab_size=cfg.vocab_size)
        self.compiler = xgr.GrammarCompiler(self.info)
        schema = json.dumps(InvoiceDraft.model_json_schema(), ensure_ascii=False)
        t0 = time.perf_counter()
        self.g_schema = self.compiler.compile_json_schema(schema)
        self.compile_schema_ms = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        self.g_json = self.compiler.compile_builtin_json_grammar()
        self.compile_json_ms = (time.perf_counter() - t0) * 1000
        self.schema_text = schema

    def gen(self, messages, mode, max_new_tokens=220):
        enc = self.tok.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt", return_dict=True)
        procs = []
        if mode == "json":
            procs = [self.xgr.contrib.hf.LogitsProcessor(self.g_json)]
        elif mode == "schema":
            procs = [self.xgr.contrib.hf.LogitsProcessor(self.g_schema)]
        t0 = time.perf_counter()
        with self.torch.no_grad():
            out = self.model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False, logits_processor=procs)
        dt = time.perf_counter() - t0
        new = out[0][enc["input_ids"].shape[1]:]
        return self.tok.decode(new, skip_special_tokens=True), len(new), dt


def strip_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        s = s.rsplit("```", 1)[0]
    return s.strip()


def judge(raw: str, gold: dict) -> dict:
    r = dict(parse=False, valid=False, sem=None, error=None)
    try:
        json.loads(strip_fence(raw))
        r["parse"] = True
    except ValueError as e:
        r["error"] = "json: " + str(e)[:60]
        return r
    try:
        d = InvoiceDraft.model_validate_json(strip_fence(raw))
        r["valid"] = True
        r["sem"] = semantic_ok(d, gold)
    except ValidationError as e:
        r["error"] = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:3])
    return r


# ---------------------------------------------------------------- l1 + l2
def l1_l2(res, n):
    llm = LLM()
    cases = [make_case(i) for i in range(n)]
    rows = {m: [] for m in ("prompt", "json", "schema")}
    retry = []
    for i, (text, gold) in enumerate(cases):
        msgs = [{"role": "system", "content": SYSTEM + llm.schema_text}, {"role": "user", "content": text}]
        for mode in rows:
            raw, ntok, dt = llm.gen(msgs, mode)
            j = judge(raw, gold)
            j.update(tokens=ntok, seconds=dt)
            rows[mode].append(j)
            if mode == "prompt":
                attempts, jj, conv = 1, j, list(msgs)
                rawk = raw
                while not jj["valid"] and attempts < 3:
                    conv = conv + [{"role": "assistant", "content": rawk},
                                   {"role": "user", "content": f"Đầu ra không hợp lệ: {jj['error']}. "
                                                               "Hãy trả lại ĐÚNG MỘT đối tượng JSON theo schema."}]
                    rawk, _, _ = llm.gen(conv, "prompt")
                    jj = judge(rawk, gold)
                    attempts += 1
                retry.append(dict(first_valid=j["valid"], final_valid=jj["valid"], attempts=attempts))
        print(f"l1 #{i:02d} " + "  ".join(f"{m}: {'V' if rows[m][-1]['valid'] else ('p' if rows[m][-1]['parse'] else '✗')}"
                                          for m in rows) + f"   retry→ {retry[-1]}")
    summ = {}
    for m, rr in rows.items():
        v = [r for r in rr if r["valid"]]
        summ[m] = dict(n=len(rr), parse=sum(r["parse"] for r in rr) / len(rr), valid=len(v) / len(rr),
                       all_fields_correct=sum(all(r["sem"].values()) for r in v) / len(rr),
                       mst_correct=sum(r["sem"]["mst"] for r in v) / len(rr),
                       total_correct=sum(r["sem"]["total"] for r in v) / len(rr),
                       tokens=sum(r["tokens"] for r in rr) / len(rr), seconds=sum(r["seconds"] for r in rr) / len(rr),
                       errors=[r["error"] for r in rr if r["error"]][:8])
        print(f"l1 {m:7s} parse {summ[m]['parse']:.0%}  hợp lệ {summ[m]['valid']:.0%}  đúng mọi trường "
              f"{summ[m]['all_fields_correct']:.0%}  token TB {summ[m]['tokens']:.0f}  {summ[m]['seconds']:.1f} s/mẫu")
    by_k = [sum(1 for r in retry if r["final_valid"] and r["attempts"] <= k) / len(retry) for k in (1, 2, 3)]
    print(f"l2 prompt thuần + retry: hợp lệ sau 1/2/3 lần gọi = {by_k}")
    res["l1_modes"] = dict(model=MODEL, summary=summ, compile_schema_ms=llm.compile_schema_ms,
                           compile_json_ms=llm.compile_json_ms, cases=n)
    res["l2_retry"] = dict(valid_by_attempts=by_k, rows=retry)
    return llm


# ---------------------------------------------------------------- l3
def l3_overhead(res, llm=None):
    import xgrammar as xgr
    llm = llm or LLM()
    text, _ = make_case(999)
    msgs = [{"role": "system", "content": SYSTEM + llm.schema_text}, {"role": "user", "content": text}]
    out = {"compile_schema_ms": llm.compile_schema_ms, "compile_json_ms": llm.compile_json_ms}
    # thời gian sinh/token với và không với processor (cùng số token: ép đủ 120 token bằng min_new_tokens)
    for mode in ("prompt", "schema"):
        times = []
        for _ in range(2):
            raw, ntok, dt = llm.gen(msgs, mode, max_new_tokens=120)
            times.append(dt / max(ntok, 1) * 1000)
        out[f"ms_per_token_{mode}"] = min(times)
    # chi phí riêng của việc tính mask: đo trực tiếp GrammarMatcher.fill_next_token_bitmask
    m = xgr.GrammarMatcher(llm.g_schema)
    bm = xgr.allocate_token_bitmask(1, llm.info.vocab_size)
    good = json.dumps(make_case(999)[1], ensure_ascii=False)
    ids = llm.tok.encode(good, add_special_tokens=False)
    t = []
    for tid in ids:
        t0 = time.perf_counter()
        m.fill_next_token_bitmask(bm)
        t.append((time.perf_counter() - t0) * 1e6)
        if not m.accept_token(tid):
            break
    t.sort()
    out.update(mask_us_p50=t[len(t) // 2], mask_us_p99=t[int(len(t) * .99)], mask_tokens=len(t), vocab=llm.info.vocab_size)
    print(f"l3 biên dịch schema {out['compile_schema_ms']:.0f} ms, JSON {out['compile_json_ms']:.0f} ms; "
          f"ms/token: không ràng buộc {out['ms_per_token_prompt']:.1f}, có ràng buộc {out['ms_per_token_schema']:.1f}; "
          f"mask p50 {out['mask_us_p50']:.0f} µs p99 {out['mask_us_p99']:.0f} µs (vocab {out['vocab']})")
    res["l3_overhead"] = out


# ---------------------------------------------------------------- l4
def l4_partial(res):
    good = json.dumps(dict(make_case(5)[1], lines=[dict(name=f"mặt hàng {i}", quantity=i + 1, unit_price=1000 * i)
                                                   for i in range(5)]), ensure_ascii=False)
    from pydantic import TypeAdapter
    out = {}
    for label, model in (("InvoiceDraft (trường bắt buộc)", InvoiceDraft), ("DraftPreview (mọi trường tùy chọn)", DraftPreview)):
        ta = TypeAdapter(model)
        rows, shown = [], []
        for cut in range(1, len(good) + 1):
            pre = good[:cut]
            t0 = time.perf_counter()
            try:
                d = ta.validate_json(pre, experimental_allow_partial="trailing-strings")
                ok, view = True, d.model_dump(exclude_defaults=True)
            except ValidationError as e:
                ok, view = False, e.errors()[0]["type"]
            rows.append(dict(chars=cut, ok=ok, us=(time.perf_counter() - t0) * 1e6))
            if cut in (40, 80, 140, 220, len(good)):
                shown.append(dict(chars=cut, prefix=pre[-50:], result=view))
        r = dict(length=len(good), validate_every_char_total_ms=sum(x["us"] for x in rows) / 1000,
                 full_validate_us=rows[-1]["us"], first_valid_prefix=next((x["chars"] for x in rows if x["ok"]), None),
                 ok_fraction=sum(x["ok"] for x in rows) / len(rows), samples=shown)
        out[label] = r
        print(f"l4 {label}: JSON {len(good)} ký tự; validate lại mỗi ký tự tổng {r['validate_every_char_total_ms']:.1f} ms "
              f"(1 lần đầy đủ {r['full_validate_us']:.0f} µs); tiền tố hợp lệ đầu tiên ở ký tự {r['first_valid_prefix']}; "
              f"{r['ok_fraction']:.0%} tiền tố validate được")
        for x in shown:
            print("     ", x["chars"], "…" + x["prefix"], "→", x["result"])
    res["l4_partial"] = out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--n", type=int, default=30)
    a = ap.parse_args()
    res = json.loads(OUT.read_text()) if OUT.exists() else {}
    llm = None
    if not a.only or "l1" in a.only:
        llm = l1_l2(res, a.n)
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    if not a.only or "l3" in a.only:
        l3_overhead(res, llm)
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    if not a.only or "l4" in a.only:
        l4_partial(res)
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
