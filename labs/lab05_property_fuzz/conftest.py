import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "lab03_invoice_api"))


@pytest.fixture(scope="session")
def auth_headers(tmp_path_factory):
    """Khởi tạo state của app (DB file tạm, khóa JWT) rồi phát một token đủ scope."""
    import asyncio

    from app.db import Database, create_schema, make_engine
    from app.main import app
    from app.security import KeyPair
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path_factory.mktemp('db') / 'fuzz.db'}")
    asyncio.run(create_schema(engine))
    app.state.engine, app.state.db, app.state.keys = engine, Database(engine), KeyPair()
    return {"authorization": f"Bearer {app.state.keys.issue('fuzz', 1, 'invoice:read invoice:write')}"}
