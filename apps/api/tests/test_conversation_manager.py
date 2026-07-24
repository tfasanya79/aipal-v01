import uuid

import pytest
from sqlalchemy import select

from app.db import async_session
from app.models import Meeting, TodayItem, User
from app.services.conversation_manager import conversation_manager


async def _user(email: str) -> User:
    async with async_session() as db:
        user = User(email=email, timezone="UTC")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


@pytest.mark.asyncio
async def test_conversation_manager_blocks_low_confidence_transcript():
    user = await _user("cm-low-confidence@example.com")
    async with async_session() as db:
        result = await conversation_manager.handle_final_transcript(
            db,
            user,
            session_id=uuid.uuid4(),
            turn_id="turn-low",
            transcript="schedule something",
            confidence=0.05,
            metrics={"stt_confidence": 0.05, "stt_no_speech_probability": 0.9},
        )

    assert result.action == "direct_reply"
    assert result.intent == "low_confidence_transcript"
    assert "didn't catch" in (result.reply or "")


@pytest.mark.asyncio
async def test_conversation_manager_collects_meeting_fields_then_confirms_to_today():
    user = await _user("cm-meeting@example.com")
    session_id = uuid.uuid4()

    async with async_session() as db:
        first = await conversation_manager.handle_final_transcript(
            db,
            user,
            session_id=session_id,
            turn_id="turn-1",
            transcript="Schedule meeting with Tobi tomorrow",
            confidence=0.9,
            metrics={"stt_confidence": 0.9, "stt_no_speech_probability": 0.0},
        )
        second = await conversation_manager.handle_final_transcript(
            db,
            user,
            session_id=session_id,
            turn_id="turn-2",
            transcript="3 PM",
            confidence=0.9,
            metrics={"stt_confidence": 0.9, "stt_no_speech_probability": 0.0},
        )
        third = await conversation_manager.handle_final_transcript(
            db,
            user,
            session_id=session_id,
            turn_id="turn-3",
            transcript="45 minutes",
            confidence=0.9,
            metrics={"stt_confidence": 0.9, "stt_no_speech_probability": 0.0},
        )
        confirmed = await conversation_manager.handle_final_transcript(
            db,
            user,
            session_id=session_id,
            turn_id="turn-4",
            transcript="Yes, save it",
            confidence=0.9,
            metrics={"stt_confidence": 0.9, "stt_no_speech_probability": 0.0},
        )

        meeting = (
            await db.execute(select(Meeting).where(Meeting.user_id == user.id))
        ).scalar_one()
        today_item = (
            await db.execute(select(TodayItem).where(TodayItem.calendar_event_id == meeting.id))
        ).scalar_one()

    assert first.action == "direct_reply"
    assert "time" in (first.reply or "").lower()
    assert "long" in (second.reply or "").lower()
    assert third.requires_confirmation is True
    assert "Should I save it" in (third.reply or "")
    assert confirmed.draft_confirmed is True
    assert meeting.title == "Meeting with Tobi"
    assert meeting.start_time.hour == 15
    assert int((meeting.end_time - meeting.start_time).total_seconds() / 60) == 45
    assert today_item.type == "meeting"


@pytest.mark.asyncio
async def test_conversation_manager_rejects_pending_confirmation_without_saving():
    user = await _user("cm-reject@example.com")
    session_id = uuid.uuid4()

    async with async_session() as db:
        draft = await conversation_manager.handle_final_transcript(
            db,
            user,
            session_id=session_id,
            turn_id="turn-1",
            transcript="Schedule meeting with Daniel tomorrow at 2 PM for one hour",
            confidence=0.95,
            metrics={"stt_confidence": 0.95, "stt_no_speech_probability": 0.0},
        )
        rejected = await conversation_manager.handle_final_transcript(
            db,
            user,
            session_id=session_id,
            turn_id="turn-2",
            transcript="No cancel",
            confidence=0.95,
            metrics={"stt_confidence": 0.95, "stt_no_speech_probability": 0.0},
        )
        meetings = list((await db.execute(select(Meeting).where(Meeting.user_id == user.id))).scalars().all())

    assert draft.requires_confirmation is True
    assert rejected.intent == "reject_pending_action"
    assert meetings == []


@pytest.mark.asyncio
async def test_conversation_manager_general_conversation_proceeds_to_brain():
    user = await _user("cm-general@example.com")
    async with async_session() as db:
        result = await conversation_manager.handle_final_transcript(
            db,
            user,
            session_id=uuid.uuid4(),
            turn_id="turn-general",
            transcript="I feel a bit tired today",
            confidence=0.9,
            metrics={"stt_confidence": 0.9, "stt_no_speech_probability": 0.0},
        )

    assert result.action == "proceed"
    assert result.intent == "general_conversation"
