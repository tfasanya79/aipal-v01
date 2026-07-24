from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_cors_reflects_localhost_origin_with_credentials():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/v2/auth/verify",
            headers={
                "Origin": "http://localhost:51140",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,authorization",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:51140"
    assert response.headers["access-control-allow-credentials"] == "true"


@pytest.mark.asyncio
async def test_cors_reflects_localhost_origin_on_auth_error_response():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v2/auth/verify",
            headers={"Origin": "http://localhost:55213"},
            json={"token": "bad-token"},
        )

    assert response.status_code == 400
    assert response.headers["access-control-allow-origin"] == "http://localhost:55213"
    assert response.headers["access-control-allow-credentials"] == "true"
