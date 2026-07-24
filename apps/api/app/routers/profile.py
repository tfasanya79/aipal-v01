from fastapi import APIRouter, Depends, Response
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..memory import memory_delete_user
from ..models import IntegrationToken, LiveSession, Task, User
from ..schemas import ProfileResponse, ProfileUpdate, str_to_time, time_to_str

router = APIRouter(tags=["profile"])


def user_to_profile(user: User) -> ProfileResponse:
    return ProfileResponse(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        wake_name=user.wake_name,
        timezone=user.timezone,
        about_me=user.about_me,
        morning_brief_at=time_to_str(user.morning_brief_at),
        evening_recap_at=time_to_str(user.evening_recap_at),
        checkin_enabled=user.checkin_enabled,
    )


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(user: User = Depends(get_current_user)):
    return user_to_profile(user)


@router.put("/profile", response_model=ProfileResponse)
async def update_profile(
    body: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.wake_name is not None:
        user.wake_name = body.wake_name
    if body.timezone is not None:
        user.timezone = body.timezone
    if body.about_me is not None:
        user.about_me = body.about_me
    if body.morning_brief_at is not None:
        user.morning_brief_at = str_to_time(body.morning_brief_at)
    if body.evening_recap_at is not None:
        user.evening_recap_at = str_to_time(body.evening_recap_at)
    if body.checkin_enabled is not None:
        user.checkin_enabled = body.checkin_enabled
    await db.commit()
    await db.refresh(user)
    return user_to_profile(user)


@router.delete("/account", status_code=204)
async def delete_account(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memory_delete_user(str(user.id))
    await db.execute(delete(Task).where(Task.user_id == user.id))
    await db.execute(delete(LiveSession).where(LiveSession.user_id == user.id))
    await db.execute(delete(IntegrationToken).where(IntegrationToken.user_id == user.id))
    await db.execute(delete(User).where(User.id == user.id))
    await db.commit()
    return Response(status_code=204)
