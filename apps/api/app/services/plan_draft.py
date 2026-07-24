import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import PlanDraft
from ..schemas import TaskCreate
from ..timezone_util import user_local_today
from . import tasks as task_svc


async def save_draft(db: AsyncSession, user_id: uuid.UUID, payload: dict) -> None:
    result = await db.execute(select(PlanDraft).where(PlanDraft.user_id == user_id))
    row = result.scalar_one_or_none()
    if row:
        row.payload = payload
        row.updated_at = datetime.now(UTC)
    else:
        db.add(PlanDraft(user_id=user_id, payload=payload))
    await db.commit()


async def get_draft(db: AsyncSession, user_id: uuid.UUID) -> dict | None:
    result = await db.execute(select(PlanDraft).where(PlanDraft.user_id == user_id))
    row = result.scalar_one_or_none()
    return row.payload if row else None


async def clear_draft(db: AsyncSession, user_id: uuid.UUID) -> None:
    result = await db.execute(select(PlanDraft).where(PlanDraft.user_id == user_id))
    row = result.scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()


def _titles_similar(a: str, b: str) -> bool:
    al = a.lower().strip()
    bl = b.lower().strip()
    if al == bl:
        return True
    if al in bl or bl in al:
        return True
    aw = set(al.split())
    bw = set(bl.split())
    return len(aw & bw) >= min(len(aw), len(bw), 1) and len(aw & bw) >= 1


async def _is_duplicate(
    db: AsyncSession,
    user_id: uuid.UUID,
    title: str,
    due_at: datetime | None,
    timezone: str,
) -> bool:
    if not due_at:
        return False
    day = user_local_today(timezone)
    existing = await task_svc.list_tasks(db, user_id, day=day, top_level_only=True)
    window = timedelta(minutes=15)
    for t in existing:
        if t.status in ("done", "skipped"):
            continue
        if not _titles_similar(t.title, title):
            continue
        if t.due_at and abs((t.due_at - due_at).total_seconds()) <= window.total_seconds():
            return True
        if t.due_at is None and due_at:
            continue
    return False


async def confirm_draft(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    timezone: str = "UTC",
) -> list[dict]:
    draft = await get_draft(db, user_id)
    if not draft:
        return []
    tasks_data = draft.get("proposed_tasks") or []
    created = []
    for idx, item in enumerate(tasks_data):
        due_at = item.get("due_at")
        if isinstance(due_at, str):
            due_at = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
        title = str(item["title"])
        item_type = str(item.get("type") or item.get("category") or "task").lower()
        if await _is_duplicate(db, user_id, title, due_at, timezone):
            continue
        if item_type == "reminder":
            from ..schemas import ReminderCreate
            from .reminder_service import create_reminder

            if due_at is None:
                continue
            reminder = await create_reminder(
                db,
                user_id,
                ReminderCreate(
                    title=title,
                    remind_at=due_at,
                    recurrence_rule=item.get("recurrence_rule"),
                    status="scheduled",
                ),
            )
            created.append({"id": reminder.id, "title": reminder.title, "due_at": reminder.remind_at, "type": "reminder"})
            continue
        if item_type == "meeting":
            from .meeting_assistant_service import create_meeting

            if due_at is None:
                continue
            end_time = item.get("end_time")
            if isinstance(end_time, str):
                end_time = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            if end_time is None:
                end_time = due_at + timedelta(minutes=int(item.get("estimated_minutes") or 60))
            meeting = await create_meeting(
                db,
                user_id,
                {
                    "title": title,
                    "start_time": due_at,
                    "end_time": end_time,
                    "participants": item.get("participants"),
                    "location": item.get("location"),
                    "notes": item.get("notes"),
                    "status": "scheduled",
                },
            )
            created.append({"id": meeting.id, "title": meeting.title, "due_at": meeting.start_time, "type": "meeting"})
            continue
        task = await task_svc.create_task(
            db,
            user_id,
            TaskCreate(
                title=title,
                notes=item.get("notes"),
                due_at=due_at,
                estimated_minutes=item.get("estimated_minutes"),
                priority=int(item.get("priority", 1)),
                category=item.get("category"),
                sort_order=idx,
                source="plan_confirm",
            ),
        )
        created.append({"id": task.id, "title": task.title, "due_at": task.due_at, "type": "task"})
    await clear_draft(db, user_id)
    return created
