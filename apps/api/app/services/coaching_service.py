from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import CoachDecision, Habit, ThinkingSession
from .goal_service import list_active_goals
from .thinking_framework_service import run_framework, suggest_framework
from .memory_service import search_memories

_DECISION_WORDS = ("should i", "which one", "which should", "what should", "help me decide", "decide between", "choose between", "compare", "tradeoff")
_STRATEGY_WORDS = ("focus on", "strategy", "roadmap", "prioritize", "prioritise", "opportunity cost", "first principles", "swot", "decision matrix", "risk reward", "pros and cons")
_ACCOUNTABILITY_WORDS = ("keep saying", "i don't do", "i do not do", "didn't do", "did not do", "i'm not doing", "i am not doing", "accountability", "follow through", "sticking with")
_HABIT_WORDS = ("every morning", "every day", "again today", "again this week", "praying", "prayer", "gym", "exercise", "reading", "meditation", "sales calls")
_GROWTH_PLAN_WORDS = ("30 day", "60 day", "90 day", "milestone", "milestones", "targets", "goal", "goals", "build a plan", "roadmap")


def _has_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _clean_title(question: str) -> str:
    text = re.sub(r"\s+", " ", question or "").strip()
    return text[:120] if text else "Coaching decision"


def detect_coaching_opportunity(message: str, context: str | None = None) -> dict[str, object] | None:
    text = f"{message} {context or ''}".lower()
    if _has_any(text, _DECISION_WORDS) and ("?" in text or "what" in text or "which" in text or "should" in text):
        return {"kind": "decision", "framework": suggest_framework(message, context), "confidence": 0.95}
    if _has_any(text, _GROWTH_PLAN_WORDS) and (any(word in text for word in ("goal", "goals", "milestone", "milestones", "target", "targets")) or any(word in text for word in ("30 day", "60 day", "90 day"))):
        return {"kind": "growth_plan", "framework": "decision_matrix", "confidence": 0.88}
    if _has_any(text, _ACCOUNTABILITY_WORDS):
        return {"kind": "accountability", "framework": "second_order_thinking", "confidence": 0.82}
    if _has_any(text, _HABIT_WORDS) and any(word in text for word in ("again", "every", "consistent", "consistently", "repeated", "repeat")):
        return {"kind": "habit", "framework": "pros_cons", "confidence": 0.8}
    if _has_any(text, _STRATEGY_WORDS) and ("?" in text or any(word in text for word in ("what", "how", "should", "help", "which", "stuck", "focus on"))):
        return {"kind": "strategy", "framework": suggest_framework(message, context), "confidence": 0.78}
    return None


async def _recent_memory_context(db: AsyncSession, user_id: UUID, query: str) -> list[str]:
    memories = await search_memories(
        db,
        user_id,
        query,
        limit=6,
        recent_summary=query,
    )
    return [f"{memory.title}: {memory.content}" for memory in memories]


async def _goal_context(db: AsyncSession, user_id: UUID) -> list[str]:
    goals = await list_active_goals(db, user_id)
    return [goal.title for goal in goals[:6]]


async def _habit_context(db: AsyncSession, user_id: UUID) -> list[str]:
    result = await db.execute(
        select(Habit.name, Habit.life_area, Habit.frequency)
        .where(Habit.user_id == user_id, Habit.status == "active")
        .order_by(Habit.created_at.desc())
        .limit(6)
    )
    return [f"{name} ({life_area or 'general'}, {frequency})" for name, life_area, frequency in result.all()]


async def create_decision_record(
    db: AsyncSession,
    user_id: UUID,
    *,
    title: str,
    question: str,
    options: list[str] | None,
    framework: str,
    analysis: dict | list | None,
    recommendation: str,
    confidence: float | None,
    selected_option: str | None = None,
) -> CoachDecision:
    record = CoachDecision(
        user_id=user_id,
        title=title,
        question=question,
        options=options,
        selected_option=selected_option,
        framework=framework,
        analysis=analysis,
        recommendation=recommendation,
        confidence=confidence or 0.0,
        status="open",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def analyze_decision(
    db: AsyncSession,
    user_id: UUID,
    question: str,
    options: list[str] | None = None,
) -> dict[str, object]:
    context = {
        "question": question,
        "options": options or [],
        "goals": await _goal_context(db, user_id),
        "recent_memories": await _recent_memory_context(db, user_id, question),
        "habits": await _habit_context(db, user_id),
    }
    framework = suggest_framework(question, " ".join(context["recent_memories"]))
    if framework == "pros_cons" and options and len(options) >= 2:
        framework = "decision_matrix"
    output = run_framework(framework, context)
    matrix = output.get("matrix") if isinstance(output, dict) else None
    confidence = 0.74
    selected_option = None
    if isinstance(matrix, list) and matrix:
        top = matrix[0]
        selected_option = str(top.get("option")) if isinstance(top, dict) else None
        if len(matrix) > 1 and isinstance(matrix[1], dict):
            gap = float(top.get("score", 0)) - float(matrix[1].get("score", 0))
            confidence = max(0.55, min(0.94, 0.58 + gap / 250))
        else:
            confidence = 0.72
    elif options:
        selected_option = options[0]

    record = await create_decision_record(
        db,
        user_id,
        title=_clean_title(question),
        question=question,
        options=options,
        framework=framework,
        analysis=output,
        recommendation=str(output.get("recommendation") or "Keep going with the cleaner option."),
        confidence=confidence,
        selected_option=None,
    )
    db.add(
        ThinkingSession(
            user_id=user_id,
            framework=framework,
            prompt=question,
            output=output,
        )
    )
    await db.commit()
    return {
        "decision_id": record.id,
        "framework": framework,
        "analysis": output,
        "recommendation": str(output.get("recommendation") or "Keep going with the cleaner option."),
        "confidence": confidence,
        "selected_option": selected_option if selected_option in (options or []) else None,
    }


async def apply_framework(
    db: AsyncSession,
    user_id: UUID,
    framework: str,
    prompt: str,
) -> dict[str, object]:
    context = {
        "prompt": prompt,
        "goals": await _goal_context(db, user_id),
        "recent_memories": await _recent_memory_context(db, user_id, prompt),
        "habits": await _habit_context(db, user_id),
    }
    output = run_framework(framework, context)
    session = ThinkingSession(
        user_id=user_id,
        framework=framework,
        prompt=prompt,
        output=output,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return {"session_id": session.id, "framework": framework, "output": output}


async def list_decisions(db: AsyncSession, user_id: UUID) -> list[CoachDecision]:
    result = await db.execute(
        select(CoachDecision)
        .where(CoachDecision.user_id == user_id)
        .order_by(CoachDecision.created_at.desc())
    )
    return list(result.scalars().all())


async def get_decision(db: AsyncSession, user_id: UUID, decision_id: UUID) -> CoachDecision | None:
    result = await db.execute(
        select(CoachDecision).where(CoachDecision.user_id == user_id, CoachDecision.id == decision_id)
    )
    return result.scalar_one_or_none()


async def coaching_context(db: AsyncSession, user_id: UUID, message: str) -> dict[str, object] | None:
    opportunity = detect_coaching_opportunity(message)
    if opportunity is None:
        return None
    if opportunity["kind"] == "decision":
        analysis = await analyze_decision(db, user_id, message, None)
        return {"kind": "decision", **analysis}
    if opportunity["kind"] == "growth_plan":
        goals = await _goal_context(db, user_id)
        return {
            "kind": "growth_plan",
            "framework": opportunity["framework"],
            "analysis": {
                "summary": "This looks like a growth-planning question.",
                "goals": goals,
            },
            "recommendation": "Offer a 30/60/90-day plan before turning it into tasks.",
            "confidence": 0.7,
        }
    if opportunity["kind"] == "accountability":
        return {
            "kind": "accountability",
            "framework": opportunity["framework"],
            "analysis": {
                "summary": "This looks like an accountability check-in.",
            },
            "recommendation": "Ask what got in the way and suggest a smaller commitment.",
            "confidence": 0.68,
        }
    if opportunity["kind"] == "habit":
        habits = await _habit_context(db, user_id)
        return {
            "kind": "habit",
            "framework": opportunity["framework"],
            "analysis": {
                "summary": "This sounds like a possible habit signal.",
                "existing_habits": habits,
            },
            "recommendation": "Nudge gently and ask permission before tracking it.",
            "confidence": 0.64,
        }
    return {
        "kind": opportunity["kind"],
        "framework": opportunity["framework"],
        "analysis": {"summary": "This may benefit from a coaching frame."},
        "recommendation": "Use a thinking framework before jumping to tasks.",
        "confidence": 0.6,
    }
