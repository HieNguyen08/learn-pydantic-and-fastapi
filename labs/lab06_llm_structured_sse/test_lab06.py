import json

import httpx
import pytest

from app import app, llm

TEXT = "Xuất hóa đơn cho Công ty TNHH Sông Hậu, MST 0100109106, thuế GTGT 8%: 2 cà phê giá 29.000, 1 bánh mì giá 25.000."


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def test_retry_sua_duoc_loi_lan_dau(client):
    llm.calls = 0
    r = await client.post("/v1/drafts", json={"text": TEXT})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["attempts"] == 2 and llm.calls == 2
    assert body["draft"]["vat_rate"] == "8" and len(body["draft"]["lines"]) == 2


async def test_loi_co_he_thong_het_lan_thu_422(client):
    r = await client.post("/v1/drafts", json={"text": TEXT.replace("Sông Hậu", "khó tính")})
    assert r.status_code == 422
    assert r.json()["detail"]["attempts"] == 3


async def test_sse_partial_roi_final(client):
    r = await client.get("/v1/drafts/stream", params={"text": TEXT})
    events = [dict(line.split(": ", 1) for line in block.split("\n")) for block in r.text.strip().split("\n\n")]
    kinds = [e["event"] for e in events]
    assert kinds[-1] == "final" and kinds.count("partial") >= 5
    first, final = json.loads(events[0]["data"]), json.loads(events[-1]["data"])
    assert set(first) <= set(final) and final["buyer_tax_code"] == "0100109106"
