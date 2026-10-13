import httpx
import pytest

from app.db import make_engine
from app.main import app
from app.security import KeyPair


@pytest.fixture
async def client(tmp_path):
    # file SQLite mới cho mỗi test; KHÔNG dùng :memory: (một kết nối chung → transaction đồng thời lẫn vào nhau)
    app.state.engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    app.state.keys = KeyPair()
    async with app.router.lifespan_context(app):                         # ASGITransport KHÔNG chạy lifespan
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            yield c
    app.state.engine = None


@pytest.fixture
def token():
    def make(tenant_id=1, scope="invoice:read invoice:write"):
        return {"authorization": f"Bearer {app.state.keys.issue('pos-1', tenant_id, scope)}"}
    return make
