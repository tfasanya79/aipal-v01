from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Task, User
from .brain_briefing_service import generate_notification_briefing
from .ui_copy import task_nudge_text


async def build_nudge_message(
    db: AsyncSession,
    user: User,
    task: Task,
    minutes: int,
) -> str:
    name = user.wake_name or user.display_name or "friend"
    title = task.title
    fallback = task_nudge_text(name, title, minutes)
    briefing = await generate_notification_briefing(
        db,
        user,
        user_message=(
            f"Create a gentle companion-style task nudge for {name}. "
            f"The task is '{title}' and it is due in about {minutes} minutes. "
            "Do not shame the user. Keep it short."
        ),
        trigger_context=f"task={title}; minutes={minutes}",
    )
    return str(briefing.get("message") or fallback)
