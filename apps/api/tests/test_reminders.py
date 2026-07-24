from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_reminder_crud_is_user_scoped():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "reminders@example.com"})
        verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
        headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}

        remind_at = datetime(2026, 6, 25, 9, 30, tzinfo=timezone.utc).isoformat()
        create = await client.post(
            "/api/v2/reminders",
            headers=headers,
            json={
                "title": "Call John",
                "remind_at": remind_at,
                "status": "scheduled",
            },
        )
        assert create.status_code == 200
        reminder_id = create.json()["id"]
        assert create.json()["title"] == "Call John"

        listed = await client.get("/api/v2/reminders", headers=headers)
        assert listed.status_code == 200
        assert any(item["id"] == reminder_id for item in listed.json())

        update = await client.patch(
            f"/api/v2/reminders/{reminder_id}",
            headers=headers,
            json={"status": "done", "title": "Call John updated"},
        )
        assert update.status_code == 200
        assert update.json()["status"] == "done"
        assert update.json()["title"] == "Call John updated"

        delete = await client.delete(f"/api/v2/reminders/{reminder_id}", headers=headers)
        assert delete.status_code == 200

        listed_after = await client.get("/api/v2/reminders", headers=headers)
        assert listed_after.status_code == 200
        assert all(item["id"] != reminder_id for item in listed_after.json())


@pytest.mark.asyncio
async def test_reminder_cannot_attach_to_foreign_task():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg1 = await client.post("/api/v2/auth/register", json={"email": "owner@example.com"})
        verify1 = await client.post("/api/v2/auth/verify", json={"token": reg1.json()["dev_token"]})
        headers1 = {"Authorization": f"Bearer {verify1.json()['access_token']}"}
        reg2 = await client.post("/api/v2/auth/register", json={"email": "other@example.com"})
        verify2 = await client.post("/api/v2/auth/verify", json={"token": reg2.json()["dev_token"]})
        headers2 = {"Authorization": f"Bearer {verify2.json()['access_token']}"}

        task = await client.post(
            "/api/v2/tasks",
            headers=headers1,
            json={"title": "Private task", "source": "text"},
        )
        assert task.status_code == 201

        remind_at = datetime(2026, 6, 25, 9, 30, tzinfo=timezone.utc).isoformat()
        create = await client.post(
            "/api/v2/reminders",
            headers=headers2,
            json={
                "title": "Should fail",
                "remind_at": remind_at,
                "task_id": task.json()["id"],
            },
        )
        assert create.status_code == 404
