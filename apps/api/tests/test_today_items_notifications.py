from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid
from unittest.mock import AsyncMock, Mock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db import async_session
from app.main import app
from app.models import Notification, Task, TodayItem, User
from app.jobs.notification_dispatcher import dispatch_due_notifications
from app.services.email_notification_service import send_email_notification


async def _authed(email: str):
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    reg = await client.post("/api/v2/auth/register", json={"email": email})
    verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
    return client, {"Authorization": f"Bearer {verify.json()['access_token']}"}, uuid.UUID(verify.json()["user_id"])


@pytest.mark.asyncio
async def test_task_creates_today_item_and_completion_syncs_task():
    client, headers, user_id = await _authed("today-task@example.com")
    try:
        due_at = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
        created = await client.post(
            "/api/v2/tasks",
            headers=headers,
            json={"title": "Finish pitch deck", "due_at": due_at, "source": "manual"},
        )
        assert created.status_code == 201
        task_id = created.json()["id"]

        items = await client.get(
            "/api/v2/today-items",
            headers=headers,
            params={"day": datetime.fromisoformat(due_at).date().isoformat()},
        )
        assert items.status_code == 200
        task_items = [item for item in items.json() if item["task_id"] == task_id]
        assert len(task_items) == 1

        completed = await client.post(f"/api/v2/today-items/{task_items[0]['id']}/complete", headers=headers)
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"

        async with async_session() as db:
            task = await db.get(Task, task_id)
            assert task is not None
            assert task.user_id == user_id
            assert task.status == "done"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_reminder_creates_today_item_and_notifications_without_duplicates():
    client, headers, _ = await _authed("today-reminder@example.com")
    try:
        remind_at = (datetime.now(UTC) + timedelta(hours=3)).isoformat()
        reminder = await client.post(
            "/api/v2/reminders",
            headers=headers,
            json={"title": "Call Estate Chairman", "remind_at": remind_at},
        )
        assert reminder.status_code == 200
        reminder_id = reminder.json()["id"]

        items = await client.get(
            "/api/v2/today-items",
            headers=headers,
            params={"day": datetime.fromisoformat(remind_at).date().isoformat()},
        )
        linked = [item for item in items.json() if item["reminder_id"] == reminder_id]
        assert len(linked) == 1
        assert linked[0]["type"] == "reminder"

        notifications = await client.get("/api/v2/notifications", headers=headers)
        assert notifications.status_code == 200
        linked_notifications = [row for row in notifications.json() if row["today_item_id"] == linked[0]["id"]]
        assert {row["channel"] for row in linked_notifications} >= {"in_app", "email"}

        updated = await client.patch(
            f"/api/v2/reminders/{reminder_id}",
            headers=headers,
            json={"title": "Call Estate Chairman", "remind_at": (datetime.now(UTC) + timedelta(hours=4)).isoformat()},
        )
        assert updated.status_code == 200
        notifications_after = await client.get("/api/v2/notifications", headers=headers)
        active = [
            row
            for row in notifications_after.json()
            if row["today_item_id"] == linked[0]["id"] and row["channel"] == "email" and row["status"] != "cancelled"
        ]
        assert len(active) == 1
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_notification_preferences_can_disable_email_notifications():
    client, headers, _ = await _authed("today-pref@example.com")
    try:
        prefs = await client.patch("/api/v2/notification-preferences", headers=headers, json={"email_enabled": False})
        assert prefs.status_code == 200
        assert prefs.json()["email_enabled"] is False

        reminder = await client.post(
            "/api/v2/reminders",
            headers=headers,
            json={"title": "No email reminder", "remind_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
        )
        assert reminder.status_code == 200
        notifications = await client.get("/api/v2/notifications", headers=headers)
        assert all(row["channel"] != "email" for row in notifications.json())
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_notification_read_dismiss_and_cross_user_scope():
    client_a, headers_a, _ = await _authed("notification-owner@example.com")
    client_b, headers_b, _ = await _authed("notification-other@example.com")
    try:
        item = await client_a.post(
            "/api/v2/today-items",
            headers=headers_a,
            json={"type": "task", "title": "Owner item", "due_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
        )
        assert item.status_code == 201
        notifications = await client_a.get("/api/v2/notifications", headers=headers_a)
        notification_id = notifications.json()[0]["id"]

        blocked = await client_b.patch(f"/api/v2/notifications/{notification_id}/read", headers=headers_b)
        assert blocked.status_code == 404

        read = await client_a.patch(f"/api/v2/notifications/{notification_id}/read", headers=headers_a)
        assert read.status_code == 200
        assert read.json()["status"] == "read"
        dismissed = await client_a.post(f"/api/v2/notifications/{notification_id}/dismiss", headers=headers_a)
        assert dismissed.status_code == 200
        assert dismissed.json()["status"] == "cancelled"
    finally:
        await client_a.aclose()
        await client_b.aclose()


@pytest.mark.asyncio
async def test_commitment_creates_today_item_and_cross_user_item_access_blocked():
    client_a, headers_a, _ = await _authed("today-commitment-owner@example.com")
    client_b, headers_b, _ = await _authed("today-commitment-other@example.com")
    try:
        follow_up_at = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
        commitment = await client_a.post(
            "/api/v2/commitments",
            headers=headers_a,
            json={
                "title": "Call 5 estate chairmen",
                "content": "I will call 5 estate chairmen tomorrow.",
                "follow_up_at": follow_up_at,
            },
        )
        assert commitment.status_code == 200
        items = await client_a.get(
            "/api/v2/today-items",
            headers=headers_a,
            params={"day": datetime.fromisoformat(follow_up_at).date().isoformat()},
        )
        linked = [item for item in items.json() if item["commitment_id"] == commitment.json()["id"]]
        assert len(linked) == 1

        blocked = await client_b.post(f"/api/v2/today-items/{linked[0]['id']}/complete", headers=headers_b)
        assert blocked.status_code == 404
    finally:
        await client_a.aclose()
        await client_b.aclose()


@pytest.mark.asyncio
async def test_companion_explicit_reminder_and_meeting_create_today_items_notifications_and_email():
    client, headers, user_id = await _authed("today-companion@example.com")
    try:
        with patch("app.services.companion_response_service.llm_chat", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Sure. I’ll remind you tomorrow at 10:00 AM."
            reminder = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={"message": "Remind me to call the estate chairman tomorrow at 10", "source": "text"},
            )
        assert reminder.status_code == 200
        assert reminder.json()["requires_confirmation"] is True
        confirm_reminder = await client.post("/api/v2/tasks/plan-draft/confirm", headers=headers)
        assert confirm_reminder.status_code == 200

        with patch("app.services.companion_response_service.llm_chat", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "I drafted the meeting with Stephen for Friday at 2:00 PM."
            meeting = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={"message": "Schedule a meeting with Stephen on Friday at 2", "source": "text"},
            )
        assert meeting.status_code == 200
        assert meeting.json()["requires_confirmation"] is True
        confirm_meeting = await client.post("/api/v2/tasks/plan-draft/confirm", headers=headers)
        assert confirm_meeting.status_code == 200

        items = await client.get("/api/v2/today-items/range", headers=headers, params={
            "start_date": datetime.now(UTC).date().isoformat(),
            "end_date": (datetime.now(UTC).date() + timedelta(days=8)).isoformat(),
        })
        assert items.status_code == 200
        types = {item["type"] for item in items.json()}
        assert "reminder" in types
        assert "meeting" in types

        async with async_session() as db:
            result = await db.execute(select(Notification).where(Notification.user_id == user_id, Notification.channel == "email"))
            assert len(result.scalars().all()) >= 2
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_companion_plan_tomorrow_creates_multiple_today_items_and_emotional_message_does_not():
    client, headers, user_id = await _authed("today-plan@example.com")
    try:
        with patch("app.services.companion_response_service.llm_chat", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Here’s a light draft for tomorrow."
            plan = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={"message": "Help me plan tomorrow", "source": "text"},
            )
        assert plan.status_code == 200
        assert plan.json()["requires_confirmation"] is True
        confirm_plan = await client.post("/api/v2/tasks/plan-draft/confirm", headers=headers)
        assert confirm_plan.status_code == 200
        async with async_session() as db:
            result = await db.execute(select(TodayItem).where(TodayItem.user_id == user_id))
            count_after_plan = len(result.scalars().all())
        assert count_after_plan >= 4

        with patch("app.services.companion_response_service.llm_chat", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "That sounds heavy. What part is weighing on you most?"
            emotional = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={"message": "I feel overwhelmed and tired", "source": "text"},
            )
        assert emotional.status_code == 200
        async with async_session() as db:
            result = await db.execute(select(TodayItem).where(TodayItem.user_id == user_id))
            assert len(result.scalars().all()) == count_after_plan
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_ambiguous_reminder_asks_clarifying_question_without_today_item():
    client, headers, user_id = await _authed("today-ambiguous@example.com")
    try:
        with patch("app.services.companion_response_service.llm_chat", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "What day and time should I remind you?"
            response = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={"message": "Remind me to call Stephen", "source": "text"},
            )
            prompt = mock_llm.call_args.args[0][1]["content"]
        assert response.status_code == 200
        assert "What day and time" in prompt
        async with async_session() as db:
            result = await db.execute(select(TodayItem).where(TodayItem.user_id == user_id))
            assert result.scalars().all() == []
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_due_notification_dispatcher_sends_pending_notifications():
    client, headers, user_id = await _authed("today-dispatch@example.com")
    try:
        created = await client.post(
            "/api/v2/today-items",
            headers=headers,
            json={"type": "task", "title": "Dispatch me", "due_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat()},
        )
        assert created.status_code == 201
        async with async_session() as db:
            result = await dispatch_due_notifications(db)
            assert result["sent"] >= 1
            rows = (
                await db.execute(
                    select(Notification).where(Notification.user_id == user_id, Notification.status == "sent")
                )
            ).scalars().all()
            assert rows
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_email_notification_uses_noop_without_smtp_and_smtp_when_configured(monkeypatch):
    client, headers, user_id = await _authed("today-email-provider@example.com")
    try:
        async with async_session() as db:
            user = await db.get(User, user_id)
            notification = Notification(
                user_id=user_id,
                title="Email test",
                body="Body",
                type="reminder",
                channel="email",
                scheduled_for=datetime.now(UTC),
            )
            db.add(notification)
            await db.commit()
            await db.refresh(notification)

            from app.services import email_notification_service as email_svc

            monkeypatch.setattr(email_svc.settings, "smtp_host", "")
            sent = await send_email_notification(db, user, notification)
            assert sent.status == "sent"
            assert sent.metadata_json["provider"] == "noop"

            notification.status = "pending"
            notification.sent_at = None
            await db.commit()
            monkeypatch.setattr(email_svc.settings, "smtp_host", "smtp.example.test")
            smtp = Mock()
            smtp.__enter__ = Mock(return_value=smtp)
            smtp.__exit__ = Mock(return_value=None)
            monkeypatch.setattr(email_svc.smtplib, "SMTP", Mock(return_value=smtp))
            sent = await send_email_notification(db, user, notification)
            assert sent.status == "sent"
            assert sent.metadata_json["provider"] == "smtp"
            assert smtp.send_message.called
    finally:
        await client.aclose()
