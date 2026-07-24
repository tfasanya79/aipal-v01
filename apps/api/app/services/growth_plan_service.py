from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Goal, GrowthPlan


def _horizon_days(horizon: str) -> int:
    mapping = {"30_day": 30, "60_day": 60, "90_day": 90}
    return mapping.get((horizon or "").lower(), 30)


def _base_title(goal: Goal | None, title: str | None, horizon: str) -> str:
    if title and title.strip():
        return title.strip()
    if goal is not None:
        return f"{goal.title} {horizon.replace('_', '-')} plan"
    return f"{horizon.replace('_', '-')} growth plan"


def _goal_keywords(goal: Goal | None, title: str) -> list[str]:
    words = []
    if goal and goal.description:
        words.append(goal.description)
    words.append(title)
    return words


def _build_plan(goal: Goal | None, title: str, horizon: str) -> dict[str, object]:
    days = _horizon_days(horizon)
    lower = f"{title} {goal.title if goal else ''}".lower()
    focus = goal.life_area if goal and goal.life_area else "business"
    if days == 30:
        milestones = [
            "Clarify the offer and success metric",
            "Reach out to the first batch of prospects",
            "Ship the smallest version of the plan",
        ]
        weekly_focus = [
            "Week 1: sharpen positioning",
            "Week 2: book conversations",
            "Week 3: learn from feedback",
            "Week 4: close the loop and review",
        ]
    elif days == 60:
        milestones = [
            "Validate the strongest channel",
            "Turn feedback into repeatable process",
            "Build a simple follow-up rhythm",
        ]
        weekly_focus = [
            "Weeks 1-2: tighten the pitch",
            "Weeks 3-4: test offers and channels",
            "Weeks 5-6: double down on traction",
            "Weeks 7-8: stabilize delivery",
        ]
    else:
        milestones = [
            "Prove the core offer",
            "Create a repeatable operating rhythm",
            "Document a clear customer story",
            "Prepare the next growth loop",
        ]
        weekly_focus = [
            "Weeks 1-4: define the path",
            "Weeks 5-8: build traction",
            "Weeks 9-12: systemize and scale",
        ]

    risks = [
        "Too many priorities at once",
        "Slow follow-up or inconsistent outreach",
        "Energy drops when progress feels uneven",
    ]
    if "sales" in lower or "customer" in lower or "estate" in lower:
        risks.append("Pipeline may stall if outreach is not consistent")
    if focus == "health":
        risks.append("Overworking can undercut energy and consistency")

    success_metrics = {
        "completed_milestones": len(milestones),
        "weekly_focus_items": len(weekly_focus),
        "review_cadence": "weekly",
    }

    summary = f"A {horizon.replace('_', '-')} plan for {title} focused on {focus}."
    return {
        "summary": summary,
        "milestones": [{"item": item, "due_week": index + 1} for index, item in enumerate(milestones)],
        "weekly_focus": [{"item": item} for item in weekly_focus],
        "risks": risks,
        "success_metrics": success_metrics,
    }


async def create_growth_plan(
    db: AsyncSession,
    user_id: UUID,
    goal_id: UUID | None = None,
    horizon: str = "30_day",
    *,
    title: str | None = None,
) -> GrowthPlan:
    goal = None
    if goal_id is not None:
        result = await db.execute(select(Goal).where(Goal.user_id == user_id, Goal.id == goal_id))
        goal = result.scalar_one_or_none()
        if goal is None:
            raise ValueError("Goal not found")
    else:
        result = await db.execute(select(Goal).where(Goal.user_id == user_id).order_by(Goal.created_at.desc()).limit(1))
        goal = result.scalar_one_or_none()
    if goal is None and not title:
        raise ValueError("Create or select a goal first")

    resolved_title = _base_title(goal, title, horizon)
    payload = _build_plan(goal, resolved_title, horizon)
    plan = GrowthPlan(
        user_id=user_id,
        goal_id=goal.id if goal is not None else goal_id,
        title=resolved_title,
        horizon=horizon,
        summary=str(payload["summary"]),
        milestones=payload["milestones"],
        weekly_focus=payload["weekly_focus"],
        risks=payload["risks"],
        success_metrics=payload["success_metrics"],
        status="active",
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


async def list_growth_plans(db: AsyncSession, user_id: UUID) -> list[GrowthPlan]:
    result = await db.execute(
        select(GrowthPlan).where(GrowthPlan.user_id == user_id).order_by(GrowthPlan.created_at.desc())
    )
    return list(result.scalars().all())


async def get_growth_plan(db: AsyncSession, user_id: UUID, plan_id: UUID) -> GrowthPlan | None:
    result = await db.execute(
        select(GrowthPlan).where(GrowthPlan.user_id == user_id, GrowthPlan.id == plan_id)
    )
    return result.scalar_one_or_none()


async def update_growth_plan(db: AsyncSession, user_id: UUID, plan_id: UUID, data: dict[str, object]) -> GrowthPlan | None:
    plan = await get_growth_plan(db, user_id, plan_id)
    if plan is None:
        return None
    for key in ("title", "summary", "milestones", "weekly_focus", "risks", "success_metrics", "status"):
        if key in data and data[key] is not None:
            setattr(plan, key, data[key])
    plan.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(plan)
    return plan
