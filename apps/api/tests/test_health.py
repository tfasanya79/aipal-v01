import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v2/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["version"] == "2.0.0"
