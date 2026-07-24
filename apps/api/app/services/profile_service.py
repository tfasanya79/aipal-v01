from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User, UserProfile


async def get_or_create_profile(db: AsyncSession, user: User) -> UserProfile:
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = UserProfile(
            user_id=user.id,
            summary=user.about_me or None,
            strengths=[],
            challenges=[],
            preferences={},
            life_areas={},
            current_projects=[],
            current_goals=[],
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    return profile


def profile_snapshot(user: User, profile: UserProfile | None) -> dict[str, object]:
    return {
        "display_name": user.display_name,
        "wake_name": user.wake_name,
        "timezone": user.timezone,
        "summary": profile.summary if profile else user.about_me,
        "strengths": profile.strengths if profile else [],
        "challenges": profile.challenges if profile else [],
        "preferences": profile.preferences if profile else {},
        "life_areas": profile.life_areas if profile else {},
        "current_projects": profile.current_projects if profile else [],
        "current_goals": profile.current_goals if profile else [],
    }
