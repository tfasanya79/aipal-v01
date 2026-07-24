"""phase 3 coaching

Revision ID: 20260623_0005_phase3_coaching
Revises: 20260623_0004_relationship_intelligence
Create Date: 2026-06-23 01:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260623_0005_phase3_coaching"
down_revision = "20260623_0004_relationship_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "coach_decisions",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("selected_option", sa.Text(), nullable=True),
        sa.Column("framework", sa.String(length=64), nullable=False),
        sa.Column("analysis", sa.JSON(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=False, server_default="0.50"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_coach_decisions_user_id", "coach_decisions", ["user_id"])

    op.create_table(
        "thinking_sessions",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("conversation_id", sa.UUID(as_uuid=True), sa.ForeignKey("conversations.id"), nullable=True),
        sa.Column("framework", sa.String(length=64), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_thinking_sessions_user_id", "thinking_sessions", ["user_id"])

    op.create_table(
        "growth_plans",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("goal_id", sa.UUID(as_uuid=True), sa.ForeignKey("goals.id"), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("horizon", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("milestones", sa.JSON(), nullable=True),
        sa.Column("weekly_focus", sa.JSON(), nullable=True),
        sa.Column("risks", sa.JSON(), nullable=True),
        sa.Column("success_metrics", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_growth_plans_user_id", "growth_plans", ["user_id"])
    op.create_index("ix_growth_plans_goal_id", "growth_plans", ["goal_id"])

    op.create_table(
        "accountability_snapshots",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("goals_summary", sa.JSON(), nullable=True),
        sa.Column("tasks_summary", sa.JSON(), nullable=True),
        sa.Column("habits_summary", sa.JSON(), nullable=True),
        sa.Column("blockers", sa.JSON(), nullable=True),
        sa.Column("score", sa.Numeric(5, 2), nullable=True),
        sa.Column("reflection", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_accountability_snapshots_user_id", "accountability_snapshots", ["user_id"])

    op.create_table(
        "habits",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("life_area", sa.String(length=32), nullable=True),
        sa.Column("frequency", sa.String(length=16), nullable=False, server_default="daily"),
        sa.Column("target_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_habits_user_id", "habits", ["user_id"])

    op.create_table(
        "habit_logs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("habit_id", sa.UUID(as_uuid=True), sa.ForeignKey("habits.id"), nullable=False),
        sa.Column("logged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_habit_logs_user_id", "habit_logs", ["user_id"])
    op.create_index("ix_habit_logs_habit_id", "habit_logs", ["habit_id"])


def downgrade() -> None:
    op.drop_index("ix_habit_logs_habit_id", table_name="habit_logs")
    op.drop_index("ix_habit_logs_user_id", table_name="habit_logs")
    op.drop_table("habit_logs")

    op.drop_index("ix_habits_user_id", table_name="habits")
    op.drop_table("habits")

    op.drop_index("ix_accountability_snapshots_user_id", table_name="accountability_snapshots")
    op.drop_table("accountability_snapshots")

    op.drop_index("ix_growth_plans_goal_id", table_name="growth_plans")
    op.drop_index("ix_growth_plans_user_id", table_name="growth_plans")
    op.drop_table("growth_plans")

    op.drop_index("ix_thinking_sessions_user_id", table_name="thinking_sessions")
    op.drop_table("thinking_sessions")

    op.drop_index("ix_coach_decisions_user_id", table_name="coach_decisions")
    op.drop_table("coach_decisions")
