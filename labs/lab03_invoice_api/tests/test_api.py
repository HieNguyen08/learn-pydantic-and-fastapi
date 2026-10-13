import asyncio
import uuid

INVOICE = {"seller_tax_code": "0100109106", "buyer": {"name": "Cty Sông Hậu"}, "issued_at": "2026-10-13T09:00:00+07:00",
           "lines": [{"name": "Cà phê", "quantity": "2", "unit_price": 29000, "vat_rate": "8", "amount": 58000}],
           "total_before_tax": 58000, "total_tax": 4640, "total": 62640}


def key():
    return {"idempotency-key": str(uuid.uuid4())}


async def test_tao_va_doc(client, token):
    r = await client.post("/v1/invoices", json=INVOICE, headers={**token(), **key()})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["number"] == 1 and body["total"] == 62640
    r = await client.get(f"/v1/invoices/{body['id']}", headers=token())
    assert r.status_code == 200 and r.json()["lines"][0]["amount"] == 58000


async def test_khong_token_401_thieu_scope_403(client, token):
    assert (await client.post("/v1/invoices", json=INVOICE, headers=key())).status_code == 401
    r = await client.post("/v1/invoices", json=INVOICE, headers={**token(scope="invoice:read"), **key()})
    assert r.status_code == 403


async def test_bola_tenant_khac_nhan_404(client, token):
    r = await client.post("/v1/invoices", json=INVOICE, headers={**token(1), **key()})
    inv_id = r.json()["id"]
    assert (await client.get(f"/v1/invoices/{inv_id}", headers=token(2))).status_code == 404


async def test_idempotency_phat_lai_va_khac_payload(client, token):
    h = {**token(), **key()}
    r1 = await client.post("/v1/invoices", json=INVOICE, headers=h)
    r2 = await client.post("/v1/invoices", json=INVOICE, headers=h)
    assert r2.status_code == 201 and r2.headers["idempotent-replayed"] == "true"
    assert r2.json()["id"] == r1.json()["id"]
    other = {**INVOICE, "buyer": {"name": "Cty khác"}}
    assert (await client.post("/v1/invoices", json=other, headers=h)).status_code == 422


async def test_so_hoa_don_lien_tuc_khi_dong_thoi(client, token):
    rs = await asyncio.gather(*(client.post("/v1/invoices", json=INVOICE, headers={**token(), **key()})
                                for _ in range(20)))
    assert all(r.status_code == 201 for r in rs)
    assert sorted(r.json()["number"] for r in rs) == list(range(1, 21))


async def test_validation_422_mst_sai(client, token):
    bad = {**INVOICE, "seller_tax_code": "0100109107"}
    r = await client.post("/v1/invoices", json=bad, headers={**token(), **key()})
    assert r.status_code == 422
    assert r.json()["detail"][0]["type"] == "tax_code_checksum"
