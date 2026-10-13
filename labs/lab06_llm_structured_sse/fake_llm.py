"""LLM giả lập, tất định — tái hiện đúng các kiểu lỗi đo được ở Module 15 (Qwen2.5-0.5B):
lần 1 trả "vat_rate": "8%" và bọc trong ```json; lần 2 (sau khi nhận lỗi) trả đúng.
Với tin nhắn chứa "khó", model sai cả 3 lần (lỗi có hệ thống)."""
import asyncio
import json
import re


class FakeLLM:
    def __init__(self, delay_per_chunk: float = 0.01):
        self.calls = 0
        self.delay = delay_per_chunk

    def _answer(self, text: str, attempt: int) -> str:
        mst = re.search(r"\b(\d{10})\b", text).group(1)
        rate = re.search(r"(\d+)\s*%", text).group(1)
        buyer = text.split(",")[0].replace("Xuất hóa đơn cho", "").strip()
        lines = [{"name": n.strip(), "quantity": int(q), "unit_price": int(p.replace(".", ""))}
                 for q, n, p in re.findall(r"(\d+) ([^,:]+?) giá ([\d.]+)", text)]
        good = {"buyer_name": buyer, "buyer_tax_code": mst, "vat_rate": rate, "lines": lines}
        if "khó" in text or attempt == 1:
            bad = {**good, "vat_rate": f"{rate}%"}
            return "```json\n" + json.dumps(bad, ensure_ascii=False) + "\n```"
        return json.dumps(good, ensure_ascii=False)

    async def complete(self, messages: list[dict]) -> str:
        self.calls += 1
        attempt = sum(1 for m in messages if m["role"] == "assistant") + 1
        await asyncio.sleep(self.delay * 5)
        return self._answer(messages[1]["content"], attempt)               # messages[1] = tin nhắn gốc của khách

    async def stream(self, messages: list[dict], chunk: int = 12):
        text = self._answer(messages[1]["content"], attempt=2)            # bản stream: giả sử đã ràng buộc schema
        for i in range(0, len(text), chunk):
            await asyncio.sleep(self.delay)
            yield text[i:i + chunk]
