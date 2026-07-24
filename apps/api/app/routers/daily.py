import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..schemas import DailyPayload, GreetingResponse, TaskNudgeResponse
from ..services import conversation as conv_svc
from ..services import plan_draft as draft_svc
from ..services import task_nudge as nudge_svc
from ..services import tasks as task_svc
from ..services.brain_briefing_service import generate_today_briefing
from ..services.proactive_conversation_service import get_or_create_preferences
from ..services.ui_copy import checkin_prompt, daily_evening_prompt, daily_morning_greeting, live_greeting_text
from ..timezone_util import user_local_today

router = APIRouter(prefix="/daily", tags=["daily"])
log = logging.getLogger("aipal.daily")


async def _safe_today_briefing(db: AsyncSession, user: User, *, user_message: str, fallback: str) -> dict[str, object]:
    try:
        return await generate_today_briefing(db, user, user_message=user_message)
    except Exception:
        log.exception("daily_brain_briefing_failed user=%s", user.id)
        return {"message": fallback, "source": "deterministic", "status": "ok"}


@router.get("/morning-payload", response_model=DailyPayload)
async def morning_payload(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    name = user.wake_name or user.display_name or "there"
    summary = await task_svc.task_summary(db, user.id, user_local_today(user.timezone))
    greeting, prompt = daily_morning_greeting(name)
    briefing = await _safe_today_briefing(
        db,
        user,
        user_message=(
            f"Good morning. Give {name} a concise Today briefing using real current context. "
            f"Task summary: total={summary.total}, done={summary.done}, open={summary.open}."
        ),
        fallback=prompt,
    )
    return DailyPayload(
        greeting=greeting,
        prompt=str(briefing.get("message") or prompt),
        summary=summary,
        source="brain",
    )


@router.get("/evening-payload", response_model=DailyPayload)
async def evening_payload(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    name = user.wake_name or user.display_name or "there"
    summary = await task_svc.task_summary(db, user.id, user_local_today(user.timezone))
    greeting, prompt = daily_evening_prompt(name, summary.total, summary.done, summary.open)
    briefing = await _safe_today_briefing(
        db,
        user,
        user_message=(
            f"Good evening. Give {name} a warm, short evening check-in using real current context. "
            f"Task summary: total={summary.total}, done={summary.done}, open={summary.open}."
        ),
        fallback=prompt,
    )
    return DailyPayload(
        greeting=greeting,
        prompt=str(briefing.get("message") or prompt),
        summary=summary,
        source="brain",
    )


@router.get("/checkin-payload", response_model=DailyPayload)
async def checkin_payload(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    name = user.wake_name or user.display_name or "there"
    greeting, prompt = checkin_prompt(name)
    briefing = await _safe_today_briefing(
        db,
        user,
        user_message=f"Create a gentle one-sentence check-in for {name}. Do not mention tasks unless relevant.",
        fallback=prompt,
    )
    return DailyPayload(
        greeting=greeting,
        prompt=str(briefing.get("message") or prompt),
        source="brain",
    )


_WAKE_HINT = (
    "You can say Hi Pal anytime to wake me — no need to tap the orb."
)


def _safe_live_greeting(
    briefing: dict[str, object],
    fallback: str,
    *,
    in_live: bool,
    wake_hint: str | None,
) -> tuple[str, str]:
    text = str(briefing.get("message") or "").strip()
    lower = text.lower()
    if not text:
        return fallback, "deterministic"
    if "deeper ai connection is offline" in lower:
        return fallback, "deterministic"
    repaired = text
    if in_live and "listening" not in lower:
        repaired = f"{repaired} I’m listening."
    if wake_hint and "hi pal" not in lower:
        repaired = f"{repaired} You can say Hi Pal anytime."
    return repaired, "brain"


@router.get("/live-greeting", response_model=GreetingResponse)
async def live_greeting(
    in_live: bool = Query(False, description="True when greeting plays after user already went Live"),
    wake_enabled: bool = Query(False, description="User has foreground wake word enabled"),
    show_wake_intro: bool = Query(False, description="Include one-time wake phrase teaching copy"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    name = user.wake_name or user.display_name or "friend"
    wake_hint = _WAKE_HINT if wake_enabled and show_wake_intro else None
    local_day = user_local_today(user.timezone)
    has_chatted = await conv_svc.has_chatted_today(db, user.id, user.timezone)
    if has_chatted:
        if in_live:
            text = live_greeting_text(name=name, hour=12, in_live=True, wake_hint=wake_hint, has_chatted_today=True)
            briefing = await _safe_today_briefing(db, user, user_message=f"Create a short Live voice greeting for {name}. They have already chatted today.", fallback=text)
            message, source = _safe_live_greeting(briefing, text, in_live=in_live, wake_hint=wake_hint)
            return GreetingResponse(text=message, wake_word_hint=wake_hint, source=source)
        draft = await draft_svc.get_draft(db, user.id)
        if draft and draft.get("proposed_tasks"):
            items = [t["title"] for t in draft["proposed_tasks"][:3]]
            text = live_greeting_text(name=name, hour=12, in_live=in_live, wake_hint=wake_hint, has_chatted_today=True, pending_items=items)
            briefing = await _safe_today_briefing(
                db,
                user,
                user_message=f"Create a short Live voice greeting for {name}. Mention the pending draft only if useful: {', '.join(items)}.",
                fallback=text,
            )
            message, source = _safe_live_greeting(briefing, text, in_live=in_live, wake_hint=wake_hint)
            return GreetingResponse(text=message, wake_word_hint=wake_hint, source=source)
        view = await task_svc.today_view(db, user.id, local_day)
        if view.up_next:
            text = live_greeting_text(name=name, hour=12, in_live=in_live, wake_hint=wake_hint, has_chatted_today=True, up_next=view.up_next.title)
            briefing = await _safe_today_briefing(db, user, user_message=f"Create a short Live voice greeting for {name}. Their up next item is {view.up_next.title}.", fallback=text)
            message, source = _safe_live_greeting(briefing, text, in_live=in_live, wake_hint=wake_hint)
            return GreetingResponse(text=message, wake_word_hint=wake_hint, source=source)
        text = live_greeting_text(name=name, hour=12, in_live=in_live, wake_hint=wake_hint, has_chatted_today=True)
        briefing = await _safe_today_briefing(db, user, user_message=f"Create a short Live voice greeting for {name}. They have already chatted today.", fallback=text)
        message, source = _safe_live_greeting(briefing, text, in_live=in_live, wake_hint=wake_hint)
        return GreetingResponse(text=message, wake_word_hint=wake_hint, source=source)

    try:
        tz = ZoneInfo(user.timezone or "UTC")
        hour = datetime.now(tz).hour
    except Exception:
        hour = 12

    text = live_greeting_text(name=name, hour=hour, in_live=in_live, wake_hint=wake_hint, has_chatted_today=False)
    briefing = await _safe_today_briefing(db, user, user_message=f"Create a short Live voice greeting for {name}. This is their first companion turn today.", fallback=text)
    message, source = _safe_live_greeting(briefing, text, in_live=in_live, wake_hint=wake_hint)
    return GreetingResponse(text=message, wake_word_hint=wake_hint, source=source)


@router.get("/task-nudge", response_model=TaskNudgeResponse)
async def task_nudge(
    task_id: int = Query(..., description="Task id to nudge for"),
    minutes: int = Query(12, ge=1, le=60, description="Minutes until due"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    preferences = await get_or_create_preferences(db, user.id)
    task = await task_svc.get_task(db, user.id, task_id)
    if not task or task.status in ("done", "skipped"):
        return TaskNudgeResponse(
            text="You're all set — nothing coming up for that item.",
            assistantMessage="You're all set — nothing coming up for that item.",
            speak=False,
            voiceId=preferences.tts_voice,
            task_id=task_id,
            minutes=minutes,
        )
    text = await nudge_svc.build_nudge_message(db, user, task, minutes)
    return TaskNudgeResponse(
        text=text,
        assistantMessage=text,
        speak=False,
        voiceId=preferences.tts_voice,
        task_id=task_id,
        minutes=minutes,
    )
