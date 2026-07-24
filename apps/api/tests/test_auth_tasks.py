from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models import MagicLinkToken


@pytest.mark.asyncio
async def test_register_verify_and_task_flow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "test@example.com"})
        assert reg.status_code == 200
        token = reg.json().get("dev_token")
        assert token

        verify = await client.post("/api/v2/auth/verify", json={"token": token})
        assert verify.status_code == 200
        access = verify.json()["access_token"]
        refresh = verify.json()["refresh_token"]
        headers = {"Authorization": f"Bearer {access}"}

        prof = await client.put(
            "/api/v2/profile",
            headers=headers,
            json={"wake_name": "James", "display_name": "James"},
        )
        assert prof.status_code == 200

        task = await client.post(
            "/api/v2/tasks",
            headers=headers,
            json={"title": "Call mom", "source": "text"},
        )
        assert task.status_code == 201

        tasks = await client.get("/api/v2/tasks", headers=headers)
        assert tasks.status_code == 200
        assert any(item["title"] == "Call mom" for item in tasks.json())

        refreshed = await client.post("/api/v2/auth/refresh", json={"refresh_token": refresh})
        assert refreshed.status_code == 200
        assert refreshed.json()["access_token"]


@pytest.mark.asyncio
async def test_root_auth_register_compatibility_route():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/auth/register", json={"email": "compat@example.com"})
        assert reg.status_code == 200
        assert reg.json().get("dev_token")


@pytest.mark.asyncio
async def test_register_rejects_invalid_email():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "not-an-email"})
        assert reg.status_code == 422


@pytest.mark.asyncio
async def test_register_rejects_empty_email():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": ""})
        assert reg.status_code == 422


@pytest.mark.asyncio
async def test_verify_rejects_invalid_token():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        verify = await client.post("/api/v2/auth/verify", json={"token": "bogus-token"})
        assert verify.status_code == 400
        assert "Invalid" in verify.json()["detail"]


@pytest.mark.asyncio
async def test_verify_rejects_expired_token():
    from app.db import async_session

    expired_token = "expired-test-token"
    async with async_session() as db:
        db.add(
            MagicLinkToken(
                token=expired_token,
                email="expired@example.com",
                expires_at=datetime.now(UTC) - timedelta(hours=1),
            )
        )
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        verify = await client.post("/api/v2/auth/verify", json={"token": expired_token})
        assert verify.status_code == 400
        assert "expired" in verify.json()["detail"].lower()


@pytest.mark.asyncio
async def test_profile_incomplete_after_verify():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "incomplete@example.com"})
        token = reg.json()["dev_token"]
        verify = await client.post("/api/v2/auth/verify", json={"token": token})
        access = verify.json()["access_token"]
        headers = {"Authorization": f"Bearer {access}"}

        prof = await client.get("/api/v2/profile", headers=headers)
        assert prof.status_code == 200
        body = prof.json()
        assert body.get("display_name") in (None, "")
        assert body.get("wake_name") in (None, "AiPal", "")
        assert body.get("display_name") in (None, "")


@pytest.mark.asyncio
async def test_profile_incomplete_vs_complete():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "profile@example.com"})
        token = reg.json()["dev_token"]
        verify = await client.post("/api/v2/auth/verify", json={"token": token})
        access = verify.json()["access_token"]
        headers = {"Authorization": f"Bearer {access}"}

        prof = await client.get("/api/v2/profile", headers=headers)
        assert prof.status_code == 200
        body = prof.json()
        assert body.get("wake_name") is None or body.get("display_name") is None

        updated = await client.put(
            "/api/v2/profile",
            headers=headers,
            json={"wake_name": "Sam", "display_name": "Sam"},
        )
        assert updated.status_code == 200
        complete = updated.json()
        assert complete["wake_name"] == "Sam"
        assert complete["display_name"] == "Sam"
