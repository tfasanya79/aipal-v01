import re
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Task
from ..schemas import TaskCreate, TaskSummary, TodaySections, TodayViewResponse
from .tool_policy import is_tool_allowed
from ..timezone_util import user_local_today


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, datetime.min.time())
    return start, start + timedelta(days=1)


def _task_on_day_clause(day: date):
    start, end = _day_bounds(day)
    return or_(
        and_(Task.due_at.is_not(None), Task.due_at >= start, Task.due_at < end),
        and_(Task.due_at.is_(None), Task.created_at >= start, Task.created_at < end),
    )


def _sort_key(task: Task) -> tuple:
    in_prog = 0 if task.status == "in_progress" else 1
    due = task.due_at or datetime.max.replace(tzinfo=UTC)
    return (in_prog, due, task.sort_order, -task.priority, task.created_at)


async def list_tasks(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    day: date | None = None,
    status: str | None = None,
    goal_id: uuid.UUID | None = None,
    top_level_only: bool = True,
) -> list[Task]:
    q = select(Task).where(Task.user_id == user_id)
    if goal_id is not None:
        q = q.where(Task.goal_id == goal_id)
    if top_level_only:
        q = q.where(Task.parent_task_id.is_(None))
    if status:
        q = q.where(Task.status == status)
    if day:
        q = q.where(_task_on_day_clause(day))
    result = await db.execute(q)
    tasks = list(result.scalars().all())
    tasks.sort(key=_sort_key)
    return tasks


async def get_task(db: AsyncSession, user_id: uuid.UUID, task_id: int) -> Task | None:
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user_id))
    return result.scalar_one_or_none()


async def _load_subtasks(db: AsyncSession, user_id: uuid.UUID, parent_ids: list[int]) -> dict[int, list[Task]]:
    if not parent_ids:
        return {}
    result = await db.execute(
        select(Task).where(Task.user_id == user_id, Task.parent_task_id.in_(parent_ids)).order_by(Task.sort_order, Task.id)
    )
    grouped: dict[int, list[Task]] = {}
    for t in result.scalars().all():
        grouped.setdefault(t.parent_task_id, []).append(t)
    return grouped


async def create_task(db: AsyncSession, user_id: uuid.UUID, data: TaskCreate) -> Task:
    task = Task(
        user_id=user_id,
        title=data.title.strip(),
        notes=data.notes,
        due_at=data.due_at,
        priority=data.priority,
        source=data.source,
        goal_id=data.goal_id,
        parent_task_id=data.parent_task_id,
        estimated_minutes=data.estimated_minutes,
        sort_order=data.sort_order,
        category=data.category,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    from .today_item_service import create_from_task

    await create_from_task(db, user_id, task)
    from .memory_manager import memory_manager
    await memory_manager.index_row(db, task)
    return task


async def bulk_create(db: AsyncSession, user_id: uuid.UUID, items: list[TaskCreate]) -> list[Task]:
    created = []
    for item in items:
        task = Task(
            user_id=user_id,
            title=item.title.strip(),
            notes=item.notes,
            due_at=item.due_at,
            priority=item.priority,
            source=item.source or "morning_brief",
            goal_id=item.goal_id,
            parent_task_id=item.parent_task_id,
            estimated_minutes=item.estimated_minutes,
            sort_order=item.sort_order,
            category=item.category,
        )
        db.add(task)
        created.append(task)
    await db.commit()
    for t in created:
        await db.refresh(t)
    from .today_item_service import create_from_task

    for t in created:
        await create_from_task(db, user_id, t)
    from .memory_manager import memory_manager
    for t in created:
        await memory_manager.index_row(db, t)
    return created


async def update_task(
    db: AsyncSession,
    user_id: uuid.UUID,
    task_id: int,
    *,
    title: str | None = None,
    status: str | None = None,
    due_at: datetime | None = None,
    notes: str | None = None,
    estimated_minutes: int | None = None,
    sort_order: int | None = None,
    category: str | None = None,
    goal_id: uuid.UUID | None = None,
) -> Task | None:
    task = await get_task(db, user_id, task_id)
    if not task:
        return None
    if title is not None:
        task.title = title
    if status is not None:
        task.status = status
        if status == "done":
            task.completed_at = datetime.now(UTC)
        elif status in ("planned", "in_progress"):
            task.completed_at = None
    if due_at is not None:
        task.due_at = due_at
    if notes is not None:
        task.notes = notes
    if estimated_minutes is not None:
        task.estimated_minutes = estimated_minutes
    if sort_order is not None:
        task.sort_order = sort_order
    if category is not None:
        task.category = category
    if goal_id is not None:
        task.goal_id = goal_id
    await db.commit()
    await db.refresh(task)
    from .today_item_service import create_from_task

    await create_from_task(db, user_id, task)
    from .memory_manager import memory_manager
    await memory_manager.index_row(db, task)
    return task


async def delete_task(db: AsyncSession, user_id: uuid.UUID, task_id: int) -> bool:
    task = await get_task(db, user_id, task_id)
    if not task:
        return False
    await db.delete(task)
    await db.commit()
    from .memory_manager import memory_manager
    await memory_manager.delete_source(db, user_id, "task", str(task_id))
    return True


async def reorder_tasks(db: AsyncSession, user_id: uuid.UUID, ordered_ids: list[int]) -> None:
    for idx, task_id in enumerate(ordered_ids):
        task = await get_task(db, user_id, task_id)
        if task:
            task.sort_order = idx
    await db.commit()


async def defer_open_tasks(db: AsyncSession, user_id: uuid.UUID, day: date) -> int:
    tasks = await list_tasks(db, user_id, day=day, top_level_only=True)
    tomorrow = datetime.combine(day + timedelta(days=1), datetime.min.time())
    count = 0
    for task in tasks:
        if task.status in ("planned", "in_progress"):
            task.status = "deferred"
            task.due_at = tomorrow + timedelta(hours=9)
            count += 1
    await db.commit()
    return count


def task_to_dict(task: Task, subtasks: list[Task] | None = None) -> dict:
    subs = subtasks or []
    return {
        "id": task.id,
        "title": task.title,
        "notes": task.notes,
        "due_at": task.due_at,
        "priority": task.priority,
        "status": task.status,
        "source": task.source,
        "goal_id": task.goal_id,
        "parent_task_id": task.parent_task_id,
        "estimated_minutes": task.estimated_minutes,
        "sort_order": task.sort_order,
        "category": task.category,
        "created_at": task.created_at,
        "completed_at": task.completed_at,
        "subtasks": [task_to_dict(st) for st in subs],
    }


async def today_view(db: AsyncSession, user_id: uuid.UUID, day: date) -> TodayViewResponse:
    from ..schemas import TaskResponse, TodayItemResponse
    from .today_item_service import list_today_items, today_item_to_dict

    all_tasks = await list_tasks(db, user_id, day=day, top_level_only=True)
    parent_ids = [t.id for t in all_tasks]
    sub_map = await _load_subtasks(db, user_id, parent_ids)

    def build_response(t: Task) -> TaskResponse:
        return TaskResponse(**task_to_dict(t, sub_map.get(t.id, [])))

    now = [build_response(t) for t in all_tasks if t.status == "in_progress"]
    upcoming = [build_response(t) for t in all_tasks if t.status in ("planned", "deferred")]
    completed = [build_response(t) for t in all_tasks if t.status == "done"]

    up_next = None
    if now:
        up_next = now[0]
    elif upcoming:
        up_next = upcoming[0]

    summary = await task_summary(db, user_id, day)
    today_items = [TodayItemResponse(**today_item_to_dict(item)) for item in await list_today_items(db, user_id, day)]
    return TodayViewResponse(
        summary=summary,
        up_next=up_next,
        sections=TodaySections(now=now, upcoming=upcoming, completed=completed),
        today_items=today_items,
    )


async def task_summary(db: AsyncSession, user_id: uuid.UUID, day: date) -> TaskSummary:
    start, end = _day_bounds(day)
    result = await db.execute(
        select(Task.status, func.count())
        .where(Task.user_id == user_id, Task.parent_task_id.is_(None), _task_on_day_clause(day))
        .group_by(Task.status)
    )
    counts = dict(result.all())
    total = sum(counts.values())
    done = counts.get("done", 0)
    deferred = counts.get("deferred", 0)
    open_count = total - done - deferred - counts.get("skipped", 0)
    streak = await _completion_streak(db, user_id)
    return TaskSummary(
        date=day.isoformat(),
        total=total,
        done=done,
        open=open_count,
        deferred=deferred,
        streak_days=streak,
    )


async def _completion_streak(db: AsyncSession, user_id: uuid.UUID) -> int:
    streak = 0
    day = date.today()
    for _ in range(30):
        start, end = _day_bounds(day)
        result = await db.execute(
            select(func.count()).where(
                Task.user_id == user_id,
                Task.status == "done",
                Task.completed_at >= start,
                Task.completed_at < end,
            )
        )
        if (result.scalar() or 0) > 0:
            streak += 1
            day -= timedelta(days=1)
        else:
            break
    return streak


async def apply_task_tools_from_text(
    db: AsyncSession,
    user_id: uuid.UUID,
    text: str,
    *,
    timezone: str = "UTC",
    mode: str | None = None,
    source: str | None = None,
) -> list[str]:
    """Simple structured tool dispatch from user text."""
    actions: list[str] = []
    t = text.lower().strip()
    day = user_local_today(timezone)

    if is_tool_allowed(mode or "companion", "view_tasks", source) and (
        "what's left" in t or "what is left" in t or "open tasks" in t
    ):
        tasks = await list_tasks(db, user_id, day=day)
        open_tasks = [x for x in tasks if x.status in ("planned", "in_progress")]
        if open_tasks:
            actions.append("Open: " + ", ".join(x.title for x in open_tasks[:6]))
        else:
            actions.append("No open tasks for today")

    if not is_tool_allowed(mode or "companion", "complete_task", source):
        return actions

    completion_patterns = [
        r"(?:mark|complete|done with)\s+(.+)",
        r"(?:finished|completed)\s+(.+)",
        r"already did\s+(.+)",
    ]
    for pattern in completion_patterns:
        if m := re.search(pattern, t):
            needle = m.group(1).strip().lower().rstrip(".")
            tasks = await list_tasks(db, user_id, day=day)
            for task in tasks:
                if task.status in ("done", "skipped"):
                    continue
                title_lower = task.title.lower()
                if needle in title_lower or title_lower in needle:
                    await update_task(db, user_id, task.id, status="done")
                    actions.append(f"Completed: {task.title}")
                    break
            if actions:
                break

    return actions


def _title_matches(task_title: str, needle: str) -> bool:
    tl = task_title.lower().strip()
    nl = needle.lower().strip()
    if nl in tl or tl in nl:
        return True
    tw = set(tl.split())
    nw = set(nl.split())
    return len(tw & nw) >= 1 and len(tw & nw) >= min(len(tw), len(nw), 1)


async def complete_tasks_from_extraction(
    db: AsyncSession,
    user_id: uuid.UUID,
    extracted: dict,
    day: date,
) -> list[str]:
    """Mark tasks done when plan extractor returns complete_task intent."""
    actions: list[str] = []
    titles = [str(t.get("title", "")).strip() for t in extracted.get("proposed_tasks") or []]
    titles = [t for t in titles if t]
    if not titles:
        return actions
    tasks = await list_tasks(db, user_id, day=day)
    for title in titles:
        for task in tasks:
            if task.status in ("done", "skipped"):
                continue
            if _title_matches(task.title, title):
                await update_task(db, user_id, task.id, status="done")
                actions.append(f"Completed: {task.title}")
                break
    return actions
