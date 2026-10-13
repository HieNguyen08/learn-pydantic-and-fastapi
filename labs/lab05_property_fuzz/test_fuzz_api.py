"""Lab 05 (phần 2) — fuzz invoice-api của Lab 03 theo OpenAPI bằng Schemathesis.

Chạy:  pytest -q test_fuzz_api.py
"""
import sys
from pathlib import Path

import schemathesis
from hypothesis import settings

sys.path.insert(0, str(Path(__file__).parents[1] / "lab03_invoice_api"))
from app.main import app  # noqa: E402

schema = schemathesis.openapi.from_asgi("/openapi.json", app)


@schema.parametrize()
@settings(max_examples=50, deadline=None)
def test_api_khong_5xx_va_dung_schema(case, auth_headers):
    case.call_and_validate(headers=auth_headers)
