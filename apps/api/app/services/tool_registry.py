"""Authoritative conversational tool catalog, validator, and executor."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date as date_type, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Meeting, User
from . import plan_draft as draft_service
from . import tasks as task_svc
from .life_map_service import get_life_map
from .memory_service import search_memories, summarize_recent_conversations
from .planner_engine_service import (
    build_planning_context,
    generate_90_day_plan,
    generate_daily_plan,
    generate_life_roadmap,
    generate_monthly_plan,
    generate_quarterly_plan,
    generate_weekly_plan,
)
from .project_room_service import create_room, get_room, summarize_room
from .today_summary_service import generate_today_summary

log = logging.getLogger("aipal.tool_registry")


class ToolRegistryError(RuntimeError):
    """Base error for registry contract failures."""


class UnknownToolError(ToolRegistryError):
    pass


class ToolArgumentError(ToolRegistryError):
    def __init__(self, tool: str, errors: list[str]) -> None:
        super().__init__(f"Invalid arguments for {tool}: {'; '.join(errors)}")
        self.tool = tool
        self.errors = errors


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PlannerArguments(ToolArguments):
    action: Literal["confirm_draft"] | None = None
    plan_kind: Literal[
        "daily", "weekly", "monthly", "quarterly", "90_day", "90-day", "life"
    ] = "daily"
    date: date_type | None = None
    week_start: date_type | None = None
    month: str | None = Field(default=None, max_length=32)
    quarter: str | None = Field(default=None, max_length=32)
    goal_id: UUID | None = None


class MeetingArguments(ToolArguments):
    meeting_id: UUID | None = None


class ProjectRoomArguments(ToolArguments):
    room_id: UUID | None = None
    room_name: str | None = Field(default=None, max_length=255)
    name: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def valid_name(self) -> "ProjectRoomArguments":
        supplied = self.room_name if self.room_name is not None else self.name
        if supplied is not None and not supplied.strip():
            raise ValueError("room name must not be blank")
        return self


class MemoryArguments(ToolArguments):
    query: str | None = Field(default=None, max_length=2_000)
    message: str | None = Field(default=None, max_length=2_000)


class EmptyArguments(ToolArguments):
    pass


class ToolExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = ""
    tool_action: str
    tool_result: Any = None
    reply: str
    mode: str = "assistant"
    ui_state: str = "tool_running"
    suggested_actions: list[dict[str, Any]] = Field(default_factory=list)
    requires_confirmation: bool = False
    confirmation_prompt: str | None = None
    plan_draft: dict[str, Any] | None = None
    narration_prompt: str | None = None
    narration_evidence: list[str] = Field(default_factory=list)

    def public_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude={"narration_prompt", "narration_evidence"})


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    db: AsyncSession
    user: User
    message: str
    source: str = "text"
    source_context: Mapping[str, Any] | None = None
    call_id: str | None = None


ToolHandler = Callable[[ToolExecutionContext, ToolArguments], Awaitable[ToolExecutionResult]]
ConfirmationPolicy = Callable[[ToolArguments], bool]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    arguments_model: type[ToolArguments]
    handler: ToolHandler
    aliases: tuple[str, ...] = ()
    confirmation_policy: ConfirmationPolicy | None = None

    @property
    def argument_names(self) -> frozenset[str]:
        return frozenset(self.arguments_model.model_fields)

    def instruction(self) -> str:
        arguments = ", ".join(sorted(self.argument_names)) or "none"
        return f"{self.name}: {self.description} Arguments: {arguments}."


class ToolRegistry:
    """Immutable single source of truth for conversational tools."""

    def __init__(self, definitions: tuple[ToolDefinition, ...]) -> None:
        by_name: dict[str, ToolDefinition] = {}
        aliases: dict[str, str] = {}
        for definition in definitions:
            if definition.name in by_name or definition.name in aliases:
                raise ValueError(f"Duplicate tool registration: {definition.name}")
            by_name[definition.name] = definition
            for alias in (definition.name, *definition.aliases):
                if alias in aliases or (alias in by_name and alias != definition.name):
                    raise ValueError(f"Duplicate tool alias: {alias}")
                aliases[alias] = definition.name
        self._definitions = tuple(definitions)
        self._by_name = by_name
        self._aliases = aliases

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(definition.name for definition in self._definitions)

    @property
    def instructions(self) -> tuple[str, ...]:
        return tuple(definition.instruction() for definition in self._definitions)

    def definition(self, name: str, *, allow_alias: bool = False) -> ToolDefinition:
        normalized = str(name or "").strip().lower()
        canonical = self._aliases.get(normalized) if allow_alias else normalized
        definition = self._by_name.get(canonical or "")
        if definition is None:
            raise UnknownToolError(f"Unknown tool: {name}")
        return definition

    def resolve(self, name: str) -> str | None:
        return self._aliases.get(str(name or "").strip().lower())

    def arguments_from_context(self, name: str, context: Mapping[str, Any] | None) -> dict[str, Any]:
        definition = self.definition(name, allow_alias=True)
        source = context or {}
        return {key: source[key] for key in definition.argument_names if key in source}

    def validate_arguments(
        self,
        name: str,
        arguments: Mapping[str, Any],
        *,
        allow_alias: bool = False,
    ) -> ToolArguments:
        definition = self.definition(name, allow_alias=allow_alias)
        if len(json.dumps(dict(arguments), default=str)) > 12_000:
            raise ToolArgumentError(definition.name, ["argument payload exceeds 12 KB"])
        try:
            return definition.arguments_model.model_validate(dict(arguments))
        except ValidationError as exc:
            errors = [
                f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
                for item in exc.errors(include_url=False)
            ]
            raise ToolArgumentError(definition.name, errors) from exc

    def requires_confirmation(self, name: str, arguments: Mapping[str, Any]) -> bool:
        definition = self.definition(name)
        validated = self.validate_arguments(name, arguments)
        return bool(
            definition.confirmation_policy
            and definition.confirmation_policy(validated)
        )

    async def execute(
        self,
        context: ToolExecutionContext,
        name: str,
        arguments: Mapping[str, Any],
        *,
        allow_alias: bool = False,
    ) -> ToolExecutionResult:
        definition = self.definition(name, allow_alias=allow_alias)
        validated = self.validate_arguments(
            definition.name,
            arguments,
        )
        started = time.perf_counter()
        try:
            result = await definition.handler(context, validated)
        except Exception as exc:
            log.exception(
                "tool_execution_failed tool=%s call_id=%s source=%s failure=%s",
                definition.name,
                context.call_id,
                context.source,
                type(exc).__name__,
            )
            raise
        duration_ms = int((time.perf_counter() - started) * 1_000)
        log.info(
            "tool_execution_completed tool=%s call_id=%s source=%s duration_ms=%d",
            definition.name,
            context.call_id,
            context.source,
            duration_ms,
        )
        return result.model_copy(update={"tool": definition.name})


def _planner_confirmation(arguments: ToolArguments) -> bool:
    return isinstance(arguments, PlannerArguments) and arguments.action == "confirm_draft"


def _project_confirmation(arguments: ToolArguments) -> bool:
    return (
        isinstance(arguments, ProjectRoomArguments)
        and arguments.room_id is None
        and bool(arguments.room_name or arguments.name)
    )


async def _planner(context: ToolExecutionContext, raw: ToolArguments) -> ToolExecutionResult:
    arguments = PlannerArguments.model_validate(raw.model_dump())
    if arguments.action == "confirm_draft":
        created = await draft_service.confirm_draft(
            context.db,
            context.user.id,
            timezone=context.user.timezone or "UTC",
        )
        names = ", ".join(str(item.get("title") or "") for item in created if item.get("title"))
        reply = f"Done, I've added {names} to Today." if names else "Got it, those items are already on Today."
        return ToolExecutionResult(
            tool_action="confirm_draft",
            tool_result={"created": created},
            reply=reply,
            mode="planner",
        )

    if arguments.plan_kind == "weekly":
        draft = await generate_weekly_plan(context.db, context.user, arguments.week_start)
    elif arguments.plan_kind == "monthly":
        draft = await generate_monthly_plan(context.db, context.user, arguments.month)
    elif arguments.plan_kind == "quarterly":
        draft = await generate_quarterly_plan(context.db, context.user, arguments.quarter)
    elif arguments.plan_kind in {"90_day", "90-day"}:
        draft = await generate_90_day_plan(context.db, context.user, arguments.goal_id)
    elif arguments.plan_kind == "life":
        draft = await generate_life_roadmap(context.db, context.user)
    else:
        source_context = dict(context.source_context or {})
        planning_context = await build_planning_context(
            context.db,
            context.user,
            user_message=context.message,
            source_context=source_context,
            target_date=arguments.date,
        )
        draft = await generate_daily_plan(
            context.db,
            context.user,
            arguments.date,
            planning_context=planning_context,
            user_message=context.message,
            source_context=source_context,
        )
    task_count = len(draft.get("proposed_tasks") or [])
    plan_kind = arguments.plan_kind.replace("_", " ")
    reply = str(draft.get("natural_response") or "").strip() or (
        f"I drafted a {plan_kind} plan with {task_count} proposed items. Review it and I can tighten the order or move things around."
    )
    return ToolExecutionResult(
        tool_action="draft_plan",
        tool_result=draft,
        reply=reply,
        mode="planner",
        plan_draft=draft,
        requires_confirmation=True,
        confirmation_prompt="Review this draft before adding it to Today.",
        suggested_actions=[
            {
                "type": "review_plan",
                "label": "Review suggested plan",
                "description": "Open the draft and decide what to keep.",
                "requires_confirmation": True,
            }
        ],
    )


async def _meeting(context: ToolExecutionContext, raw: ToolArguments) -> ToolExecutionResult:
    arguments = MeetingArguments.model_validate(raw.model_dump())
    selected: Meeting | None = None
    action = "brief_meeting"
    if arguments.meeting_id is not None:
        selected = (
            await context.db.execute(
                select(Meeting).where(
                    Meeting.user_id == context.user.id,
                    Meeting.id == arguments.meeting_id,
                )
            )
        ).scalar_one_or_none()
    if selected is None:
        selected = (
            await context.db.execute(
                select(Meeting)
                .where(
                    Meeting.user_id == context.user.id,
                    Meeting.status != "cancelled",
                    Meeting.start_time >= datetime.now(UTC),
                )
                .order_by(Meeting.start_time.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        action = "brief_next_meeting"
    if selected is None:
        return ToolExecutionResult(
            tool_action="none",
            reply="I could not find a meeting to brief yet. Add a meeting and I will prepare it here.",
            ui_state="idle",
        )
    result = {
        "meeting_id": str(selected.id),
        "title": selected.title,
        "start_time": selected.start_time.isoformat() if selected.start_time else None,
        "notes": (selected.notes or "")[:600],
        "participants": selected.participants or [],
    }
    evidence = [
        f"Meeting title: {selected.title}",
        f"Start time: {result['start_time'] or 'unscheduled'}",
        f"Notes: {result['notes']}",
        f"Participants: {result['participants']}",
    ]
    return ToolExecutionResult(
        tool_action=action,
        tool_result=result,
        reply=_meeting_fallback(selected),
        narration_prompt="Give a concise meeting preparation brief.",
        narration_evidence=evidence,
    )


async def _project_room(context: ToolExecutionContext, raw: ToolArguments) -> ToolExecutionResult:
    arguments = ProjectRoomArguments.model_validate(raw.model_dump())
    if arguments.room_id is not None:
        room = await get_room(context.db, context.user.id, arguments.room_id)
        summary = await summarize_room(context.db, context.user.id, arguments.room_id)
        if room is not None and summary is not None:
            return ToolExecutionResult(
                tool_action="summarize_room",
                tool_result=summary,
                reply=f"Here is the latest summary for {room.name}.",
                narration_prompt="Summarize the project room in a companion voice.",
                narration_evidence=[f"Room name: {room.name}", str(summary.get("summary") or "")],
            )
    room_name = arguments.room_name or arguments.name
    if room_name:
        room = await create_room(context.db, context.user.id, room_name)
        summary = await summarize_room(context.db, context.user.id, room.id)
        fallback = f"I created the {room.name} room and linked what I could find so far. You can ask me to summarize it or attach more context later."
        return ToolExecutionResult(
            tool_action="create_room",
            tool_result=summary,
            reply=fallback,
            narration_prompt="Confirm that the project room was created and summarize what was linked.",
            narration_evidence=[f"Room name: {room.name}", str((summary or {}).get("summary") or "")],
        )
    return ToolExecutionResult(
        tool_action="none",
        reply="Tell me the project name and I will create the room from Companion.",
        ui_state="idle",
    )


async def _life_map(context: ToolExecutionContext, raw: ToolArguments) -> ToolExecutionResult:
    del raw
    result = await get_life_map(context.db, context.user.id)
    areas = [area for area in result.get("areas", []) if isinstance(area, dict)]
    fallback = _life_map_fallback(result)
    evidence = [
        f"{area.get('label')}: progress {area.get('progress')} with {area.get('task_count')} tasks, {area.get('goal_count')} goals, {area.get('memory_count')} memories"
        for area in areas[:4]
    ]
    return ToolExecutionResult(
        tool_action="brief_life_map",
        tool_result=result,
        reply=fallback,
        mode="companion",
        narration_prompt=None if result.get("sparse") or not areas else "Brief the user on their Life Map in a warm, concise way.",
        narration_evidence=evidence,
    )


async def _today(context: ToolExecutionContext, raw: ToolArguments, *, tool_action: str, mode: str, empty: str, prompt: str) -> ToolExecutionResult:
    del raw
    agenda = await generate_today_summary(context.db, context.user)
    body = str(agenda.get("body") or "").strip()
    has_items = bool((agenda.get("agenda", {}) or {}).get("items"))
    return ToolExecutionResult(
        tool_action=tool_action,
        tool_result=agenda,
        reply=body if has_items and body else empty,
        mode=mode,
        narration_prompt=prompt if has_items else None,
        narration_evidence=[body] if body else [],
    )


async def _morning_brief(context: ToolExecutionContext, raw: ToolArguments) -> ToolExecutionResult:
    return await _today(
        context,
        raw,
        tool_action="morning_brief",
        mode="companion",
        empty="I don't have any agenda items yet. Add a task, reminder, or calendar item and I’ll turn it into a brief.",
        prompt="Deliver a morning brief that sounds like a helpful companion.",
    )


async def _calendar(context: ToolExecutionContext, raw: ToolArguments) -> ToolExecutionResult:
    return await _today(
        context,
        raw,
        tool_action="today_summary",
        mode="assistant",
        empty="I don’t have any calendar or today items yet. Add one and I’ll turn it into a brief.",
        prompt="Explain today's agenda in a companion voice.",
    )


async def _memory(context: ToolExecutionContext, raw: ToolArguments) -> ToolExecutionResult:
    arguments = MemoryArguments.model_validate(raw.model_dump())
    query = arguments.query or arguments.message or context.message
    memories = await search_memories(context.db, context.user.id, query, limit=5)
    conversation = await summarize_recent_conversations(context.db, context.user.id, limit=5)
    return ToolExecutionResult(
        tool_action="memory_lookup",
        tool_result={"matches": memories, "conversation": conversation},
        reply=_memory_fallback(len(memories), conversation),
        mode="companion",
        narration_prompt="Explain what memory context was found.",
        narration_evidence=[f"Memory matches: {len(memories)}", f"Recent thread: {conversation}"],
    )


async def _tasks(context: ToolExecutionContext, raw: ToolArguments) -> ToolExecutionResult:
    del raw
    tasks = await task_svc.list_tasks(context.db, context.user.id)
    open_tasks = [
        task for task in tasks
        if task.status not in {"done", "completed", "cancelled", "dismissed"}
    ]
    return ToolExecutionResult(
        tool_action="task_summary",
        tool_result={"open_tasks": [task_svc.task_to_dict(task) for task in open_tasks[:12]]},
        reply=_task_fallback(open_tasks),
        narration_prompt="Summarize the user's open tasks.",
        narration_evidence=[task.title for task in open_tasks[:10]],
    )


def _meeting_fallback(meeting: Meeting) -> str:
    when = meeting.start_time.isoformat() if meeting.start_time else "unscheduled"
    extras = [name for name, present in (("notes", meeting.notes), ("participants", meeting.participants)) if present]
    suffix = f" with {' and '.join(extras)}" if extras else ""
    return f"I found {meeting.title} on your calendar for {when}{suffix}. I can help you prep a brief or action list from here."


def _life_map_fallback(life_map: Mapping[str, Any]) -> str:
    areas = [area for area in life_map.get("areas", []) if isinstance(area, dict)]
    if not areas or life_map.get("sparse"):
        return "I don’t have enough life map data yet. Share a few goals, tasks, or memories and I’ll build it out."
    top = sorted(areas, key=lambda item: int(item.get("progress") or 0), reverse=True)[:2]
    labels = [str(area.get("label") or area.get("life_area") or "an area") for area in top]
    return f"Your Life Map is strongest in {' and '.join(labels)}. Ask me to zoom in and I’ll unpack the details."


def _memory_fallback(match_count: int, conversation: str) -> str:
    if match_count <= 0:
        return "I don’t have any memory matches yet. Give me a person, project, or phrase and I’ll search again."
    suffix = " and I’m using the recent conversation context too" if conversation else ""
    return f"I found {match_count} memory match{'es' if match_count != 1 else ''}{suffix}."


def _task_fallback(tasks: list[Any]) -> str:
    if not tasks:
        return "You don’t have any open tasks right now."
    titles = ", ".join(str(task.title) for task in tasks[:3] if getattr(task, "title", None))
    suffix = f", including {titles}" if titles else ""
    return f"You have {len(tasks)} open task{'s' if len(tasks) != 1 else ''}{suffix}. I can help sort the order."


tool_registry = ToolRegistry(
    (
        ToolDefinition(
            name="planner_engine",
            aliases=("plan_my_day", "daily_plan", "weekly_plan", "monthly_plan", "quarterly_plan", "life_roadmap"),
            description="Draft plans or apply a previously confirmed planner draft.",
            arguments_model=PlannerArguments,
            confirmation_policy=_planner_confirmation,
            handler=_planner,
        ),
        ToolDefinition(
            name="meeting_assistant",
            description="Brief an owned meeting or the next upcoming meeting.",
            arguments_model=MeetingArguments,
            handler=_meeting,
        ),
        ToolDefinition(
            name="project_rooms",
            aliases=("project_room",),
            description="Summarize an owned project room or create one after confirmation.",
            arguments_model=ProjectRoomArguments,
            confirmation_policy=_project_confirmation,
            handler=_project_room,
        ),
        ToolDefinition(
            name="life_map",
            description="Read and summarize the user's Life Map.",
            arguments_model=EmptyArguments,
            handler=_life_map,
        ),
        ToolDefinition(
            name="morning_brief",
            description="Read today's grounded morning brief.",
            arguments_model=EmptyArguments,
            handler=_morning_brief,
        ),
        ToolDefinition(
            name="memory_service",
            description="Semantically retrieve relevant memories and recent discussions.",
            arguments_model=MemoryArguments,
            handler=_memory,
        ),
        ToolDefinition(
            name="calendar_service",
            description="Read today's calendar and agenda context.",
            arguments_model=EmptyArguments,
            handler=_calendar,
        ),
        ToolDefinition(
            name="task_service",
            description="Read and summarize the user's open tasks.",
            arguments_model=EmptyArguments,
            handler=_tasks,
        ),
    )
)
