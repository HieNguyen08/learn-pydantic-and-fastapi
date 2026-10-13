"""Lab 06 — structured output: validate–retry + SSE partial (Module 15).

Chạy:  uvicorn app:app --port 8200
       curl -N "http://127.0.0.1:8200/v1/drafts/stream?text=..."
"""
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, TypeAdapter, ValidationError

from fake_llm import FakeLLM
from models import DraftPreview, InvoiceDraft

SYSTEM = "Trích hóa đơn từ tin nhắn. Chỉ trả về JSON theo schema: " + str(InvoiceDraft.model_json_schema())
MAX_ATTEMPTS = 3
llm = FakeLLM()
preview = TypeAdapter(DraftPreview)
app = FastAPI(title="ai-gateway (Lab 06)")


def strip_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1].rsplit("```", 1)[0]
    return s.strip()


class DraftRequest(BaseModel):
    text: Annotated[str, Query(min_length=5, max_length=2000)]


class DraftResult(BaseModel):
    draft: InvoiceDraft
    attempts: int


@app.post("/v1/drafts", response_model=DraftResult, responses={422: {}})
async def create_draft(req: DraftRequest):
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": req.text}]
    errors = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        raw = await llm.complete(messages)
        try:
            return DraftResult(draft=InvoiceDraft.model_validate_json(strip_fence(raw)), attempts=attempt)
        except ValidationError as e:
            errors = e.errors(include_url=False, include_input=False)       # không gửi lại input (PII)
            messages = messages + [{"role": "assistant", "content": raw},
                                   {"role": "user", "content": f"Đầu ra không hợp lệ: {errors}. Trả lại đúng JSON."}]
    raise HTTPException(422, {"title": "LLM không tạo được bản nháp hợp lệ", "attempts": MAX_ATTEMPTS,
                              "errors": errors})


@app.get("/v1/drafts/stream", response_class=EventSourceResponse)
async def stream_draft(text: Annotated[str, Query(min_length=5, max_length=2000)]):
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}]
    buf, seq = "", 0
    async for chunk in llm.stream(messages):
        buf += chunk
        part = preview.validate_json(buf, experimental_allow_partial="trailing-strings")
        seq += 1
        yield ServerSentEvent(event="partial", id=str(seq), data=part.model_dump(exclude_defaults=True))
    try:
        final = InvoiceDraft.model_validate_json(buf)                     # kiểm đầy đủ, kể cả checksum MST
        yield ServerSentEvent(event="final", id=str(seq + 1), data=final.model_dump())
    except ValidationError as e:
        yield ServerSentEvent(event="error", id=str(seq + 1),
                              data={"errors": e.errors(include_url=False, include_input=False)})
