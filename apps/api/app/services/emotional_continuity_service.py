from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from statistics import mean
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import EmotionalPattern, EmotionalState


async def get_emotional_continuity(db: AsyncSession, user_id: UUID) -> dict[str, object]:
    end = datetime.now(UTC)
    start = end - timedelta(days=60)
    result = await db.execute(
        select(EmotionalState).where(
            EmotionalState.user_id == user_id,
            EmotionalState.created_at >= start,
        ).order_by(EmotionalState.created_at.asc())
    )
    emotions = list(result.scalars().all())
    if not emotions:
        return {"patterns": [], "summary": "Not enough emotional data yet."}
    mid = max(len(emotions) // 2, 1)
    first = emotions[:mid]
    second = emotions[mid:]
    first_avg = mean([e.intensity for e in first]) if first else 0
    second_avg = mean([e.intensity for e in second]) if second else first_avg
    direction = "held steady"
    if second_avg >= first_avg + 0.5:
        direction = "moved upward"
    elif second_avg <= first_avg - 0.5:
        direction = "dipped"
    counts = Counter(item.emotion for item in emotions)
    top_emotion = counts.most_common(1)[0][0]
    pattern = EmotionalPattern(
        user_id=user_id,
        pattern_type="trend",
        emotion=top_emotion,
        life_area=None,
        summary=f"Your emotions seem to have {direction} over the last two months.",
        evidence=[
            {"emotion": item.emotion, "intensity": item.intensity, "date": item.created_at.isoformat()}
            for item in emotions[-8:]
        ],
        confidence=min(0.95, 0.55 + abs(second_avg - first_avg) * 0.12),
        period_start=start.date(),
        period_end=end.date(),
    )
    db.add(pattern)
    await db.commit()
    await db.refresh(pattern)
    return {
        "patterns": [
            {
                "pattern_type": pattern.pattern_type,
                "emotion": pattern.emotion,
                "life_area": pattern.life_area,
                "summary": pattern.summary,
                "confidence": float(pattern.confidence),
                "period_start": pattern.period_start,
                "period_end": pattern.period_end,
                "evidence": pattern.evidence or [],
            }
        ],
        "summary": pattern.summary,
    }

