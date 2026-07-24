import json
import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Task
from ..schemas import TaskCreate
from . import tasks as task_svc


async def breakdown_task(db: AsyncSession, user_id: uuid.UUID, task: Task) -> list[Task]:
    existing = await task_svc._load_subtasks(db, user_id, [task.id])
    if existing.get(task.id):
        return existing[task.id]

    items = _heuristic_breakdown(task.title, task.estimated_minutes)

    created = []
    for idx, item in enumerate(items[:6]):
        sub = await task_svc.create_task(
            db,
            user_id,
            TaskCreate(
                title=str(item["title"])[:500],
                estimated_minutes=int(item.get("estimated_minutes", 15)),
                goal_id=task.goal_id,
                parent_task_id=task.id,
                sort_order=idx,
                source="breakdown",
                due_at=task.due_at,
                category=task.category,
            ),
        )
        created.append(sub)

    total_mins = sum(s.estimated_minutes or 0 for s in created)
    if total_mins and not task.estimated_minutes:
        await task_svc.update_task(db, user_id, task.id, estimated_minutes=total_mins)

    return created


def _parse_breakdown_json(raw: str) -> list[dict]:
    text = raw.strip()
    if m := re.search(r"\[[\s\S]*\]", text):
        text = m.group(0)
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("expected list")
    out = []
    for item in data:
        if isinstance(item, dict) and item.get("title"):
            mins = item.get("estimated_minutes", 15)
            out.append({"title": str(item["title"]), "estimated_minutes": max(5, min(60, int(mins)))})
    if len(out) < 2:
        raise ValueError("too few items")
    return out


def _heuristic_breakdown(title: str, estimated_minutes: int | None = None) -> list[dict]:
    clean = re.sub(r"\s+", " ", title.strip())[:80] or "task"
    lower = clean.lower()
    total = estimated_minutes or 45
    short = max(10, min(30, total // 3 if total >= 30 else 10))

    if any(word in lower for word in ("call", "phone", "chairmen", "customer", "client")):
        return [
            {"title": f"Prepare notes for {clean}", "estimated_minutes": short},
            {"title": f"Make {clean}", "estimated_minutes": max(15, short)},
            {"title": "Log outcome and follow up", "estimated_minutes": short},
        ]
    if any(word in lower for word in ("demo", "presentation", "pitch")):
        return [
            {"title": f"Outline {clean}", "estimated_minutes": short},
            {"title": "Rehearse key points", "estimated_minutes": max(15, short)},
            {"title": "Send follow-up notes", "estimated_minutes": short},
        ]
    if any(word in lower for word in ("write", "draft", "document", "proposal")):
        return [
            {"title": f"Outline {clean}", "estimated_minutes": short},
            {"title": f"Draft {clean}", "estimated_minutes": max(20, short)},
            {"title": "Review and polish", "estimated_minutes": short},
        ]
    if any(word in lower for word in ("gym", "workout", "swim", "run")):
        return [
            {"title": "Get ready", "estimated_minutes": 10},
            {"title": clean, "estimated_minutes": max(20, total)},
            {"title": "Cool down and log it", "estimated_minutes": 10},
        ]
    return [
        {"title": f"Prepare for {clean}", "estimated_minutes": short},
        {"title": clean, "estimated_minutes": max(15, total - short)},
        {"title": "Review next step", "estimated_minutes": 10},
    ]
