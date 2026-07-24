from datetime import date
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..schemas import (
    PlanDraftResponse,
    ProposedTask,
    SuggestDayRequest,
    SuggestDayResponse,
    GoalSummaryResponse,
    TaskBulkCreate,
    TaskCreate,
    TaskDetailResponse,
    TaskReorderRequest,
    TaskResponse,
    TaskSummary,
    TaskUpdate,
    TodayViewResponse,
)
from ..services import plan_draft as draft_svc
from ..services import suggest_day as suggest_day_svc
from ..services import tasks as task_svc
from ..services import task_planner
from ..timezone_util import user_local_today

router = APIRouter(prefix="/tasks", tags=["tasks"])


def to_response(t, subtasks=None) -> TaskResponse:
    subs = subtasks or []
    return TaskResponse(
        id=t.id,
        title=t.title,
        notes=t.notes,
        due_at=t.due_at,
        priority=t.priority,
        status=t.status,
        source=t.source,
        goal_id=t.goal_id,
        parent_task_id=t.parent_task_id,
        estimated_minutes=t.estimated_minutes,
        sort_order=t.sort_order,
        category=t.category,
        created_at=t.created_at,
        completed_at=t.completed_at,
        subtasks=[to_response(st) for st in subs],
    )


def to_detail_response(t, subtasks=None, goal=None) -> TaskDetailResponse:
    base = to_response(t, subtasks)
    linked_goal = None
    if goal is not None:
        linked_goal = GoalSummaryResponse(
            id=goal.id,
            title=goal.title,
            description=goal.description,
            life_area=goal.life_area,
            status=goal.status,
            priority=goal.priority,
            target_date=goal.target_date,
            created_at=goal.created_at,
            updated_at=goal.updated_at,
        )
    return TaskDetailResponse(**base.model_dump(), linked_goal=linked_goal)


@router.get("/plan-draft", response_model=PlanDraftResponse | None)
async def get_plan_draft(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    draft = await draft_svc.get_draft(db, user.id)
    if not draft or not draft.get("proposed_tasks"):
        return None
    return PlanDraftResponse(
        intent=draft.get("intent", "plan_day"),
        proposed_tasks=[ProposedTask(**t) for t in draft["proposed_tasks"]],
        clarifying_question=draft.get("clarifying_question"),
    )


@router.post("/plan-draft/confirm")
async def confirm_plan_draft(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    created = await draft_svc.confirm_draft(db, user.id, timezone=user.timezone or "UTC")
    return {"ok": True, "created": created}


@router.post("/plan-draft/discard")
async def discard_plan_draft(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await draft_svc.clear_draft(db, user.id)
    return {"ok": True}


def _draft_to_schema(payload: dict | None) -> PlanDraftResponse | None:
    if not payload or not payload.get("proposed_tasks"):
        return None
    return PlanDraftResponse(
        intent=payload.get("intent", "plan_day"),
        proposed_tasks=[ProposedTask(**t) for t in payload["proposed_tasks"]],
        clarifying_question=payload.get("clarifying_question"),
    )


@router.post("/suggest-day", response_model=SuggestDayResponse)
async def suggest_day(
    body: SuggestDayRequest = SuggestDayRequest(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    extracted = await suggest_day_svc.suggest_day(db, user, template=body.template)
    return SuggestDayResponse(plan_draft=_draft_to_schema(extracted))


@router.get("/today-view", response_model=TodayViewResponse)
async def today_view(
    day: date | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    d = day or user_local_today(user.timezone)
    return await task_svc.today_view(db, user.id, d)


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    day: date | None = None,
    status: str | None = None,
    goal_id: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await task_svc.list_tasks(
        db,
        user.id,
        day=day,
        status=status,
        goal_id=uuid.UUID(goal_id) if goal_id else None,
    )
    sub_map = await task_svc._load_subtasks(db, user.id, [t.id for t in items])
    return [to_response(t, sub_map.get(t.id, [])) for t in items]


@router.get("/{task_id}/detail", response_model=TaskDetailResponse)
async def task_detail(
    task_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await task_svc.get_task(db, user.id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    sub_map = await task_svc._load_subtasks(db, user.id, [task.id])
    goal = None
    if task.goal_id is not None:
        from ..models import Goal

        result = await db.execute(select(Goal).where(Goal.user_id == user.id, Goal.id == task.goal_id))
        goal = result.scalar_one_or_none()
    return to_detail_response(task, sub_map.get(task.id, []), goal)


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(
    body: TaskCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await task_svc.create_task(db, user.id, body)
    return to_response(task)


@router.post("/bulk", response_model=list[TaskResponse], status_code=201)
async def bulk_create(
    body: TaskBulkCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    created = await task_svc.bulk_create(db, user.id, body.tasks)
    return [to_response(t) for t in created]


@router.post("/reorder")
async def reorder_tasks(
    body: TaskReorderRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await task_svc.reorder_tasks(db, user.id, body.ordered_ids)
    return {"ok": True}


@router.post("/defer-open")
async def defer_open(
    day: date | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    d = day or date.today()
    count = await task_svc.defer_open_tasks(db, user.id, d)
    return {"deferred": count}


@router.get("/summary", response_model=TaskSummary)
async def summary(
    day: date | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    d = day or date.today()
    return await task_svc.task_summary(db, user.id, d)


@router.post("/{task_id}/breakdown", response_model=list[TaskResponse])
async def breakdown_task(
    task_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await task_svc.get_task(db, user.id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    subs = await task_planner.breakdown_task(db, user.id, task)
    return [to_response(s) for s in subs]


@router.patch("/{task_id}", response_model=TaskResponse)
async def patch_task(
    task_id: int,
    body: TaskUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await task_svc.update_task(
        db,
        user.id,
        task_id,
        title=body.title,
        status=body.status,
        due_at=body.due_at,
        notes=body.notes,
        estimated_minutes=body.estimated_minutes,
        sort_order=body.sort_order,
        category=body.category,
        goal_id=body.goal_id,
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    sub_map = await task_svc._load_subtasks(db, user.id, [task.id])
    return to_response(task, sub_map.get(task.id, []))


@router.delete("/{task_id}")
async def delete_task(
    task_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deleted = await task_svc.delete_task(db, user.id, task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True}
