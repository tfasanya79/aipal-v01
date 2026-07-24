from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from sqlalchemy import select

from app.db import async_session
from app.models import Meeting, Reminder, TodayItem, User


@pytest.mark.asyncio
async def test_whisper_streaming_stt_exposes_final_confidence_metrics():
    from app.config import Settings
    from app.services.whisper_streaming_stt import WhisperStreamingSTT

    settings = Settings(whisper_stream_partial_interval_ms=0)
    stt = WhisperStreamingSTT(settings)
    pcm = (np.zeros(16000, dtype=np.int16)).tobytes()

    async def fake_transcribe(*, beam_size):
        return "schedule a meeting tomorrow", {
            "stt_confidence": 0.91,
            "stt_no_speech_probability": 0.04,
        }

    stt._transcribe_with_meta = fake_transcribe  # type: ignore[method-assign]
    await stt.on_speech_start()
    await stt.feed_audio(pcm)
    result = await stt.on_speech_end()
    metrics = stt.consume_metrics()

    assert result.text == "schedule a meeting tomorrow"
    assert result.confidence == 0.91
    assert metrics["stt_confidence"] == 0.91
    assert metrics["stt_no_speech_probability"] == 0.04


@pytest.mark.asyncio
async def test_confirming_reminder_draft_creates_reminder_and_today_item():
    from app.services import plan_draft

    async with async_session() as db:
        user = User(email="voice-reminder-draft@example.com", timezone="UTC")
        db.add(user)
        await db.commit()
        await db.refresh(user)

        remind_at = datetime.now(UTC) + timedelta(days=1, hours=2)
        await plan_draft.save_draft(
            db,
            user.id,
            {
                "intent": "reminder_confirmation",
                "proposed_tasks": [
                    {
                        "type": "reminder",
                        "title": "Pay rent",
                        "due_at": remind_at.isoformat(),
                        "notes": "Remind me to pay rent tomorrow.",
                    }
                ],
            },
        )
        created = await plan_draft.confirm_draft(db, user.id, timezone="UTC")

        assert created and created[0]["type"] == "reminder"
        reminder = (
            await db.execute(select(Reminder).where(Reminder.user_id == user.id))
        ).scalar_one()
        today_item = (
            await db.execute(
                select(TodayItem).where(TodayItem.reminder_id == reminder.id)
            )
        ).scalar_one()
        assert reminder.title == "Pay rent"
        assert today_item.title == "Pay rent"
        assert today_item.type == "reminder"


@pytest.mark.asyncio
async def test_confirming_meeting_draft_creates_meeting_and_today_item():
    from app.services import plan_draft

    async with async_session() as db:
        user = User(email="voice-meeting-draft@example.com", timezone="UTC")
        db.add(user)
        await db.commit()
        await db.refresh(user)

        starts_at = datetime.now(UTC) + timedelta(days=2, hours=3)
        await plan_draft.save_draft(
            db,
            user.id,
            {
                "intent": "meeting_confirmation",
                "proposed_tasks": [
                    {
                        "type": "meeting",
                        "title": "Meeting with John",
                        "due_at": starts_at.isoformat(),
                        "end_time": (starts_at + timedelta(hours=1)).isoformat(),
                        "location": "Wuse 2",
                        "participants": ["John"],
                    }
                ],
            },
        )
        created = await plan_draft.confirm_draft(db, user.id, timezone="UTC")

        assert created and created[0]["type"] == "meeting"
        meeting = (
            await db.execute(select(Meeting).where(Meeting.user_id == user.id))
        ).scalar_one()
        today_item = (
            await db.execute(
                select(TodayItem).where(TodayItem.calendar_event_id == meeting.id)
            )
        ).scalar_one()
        assert meeting.title == "Meeting with John"
        assert meeting.location == "Wuse 2"
        assert today_item.title == "Meeting with John"
        assert today_item.type == "meeting"
