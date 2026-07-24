"""today items and notifications

Revision ID: 20260627_0011_today_items_notifications
Revises: 20260626_0010_companion_tts_voice
Create Date: 2026-06-27 09:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260627_0011_today_items_notifications"
down_revision = "20260626_0010_companion_tts_voice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "today_items",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("priority", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column("goal_id", sa.UUID(as_uuid=True), sa.ForeignKey("goals.id"), nullable=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("calendar_event_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("reminder_id", sa.UUID(as_uuid=True), sa.ForeignKey("reminders.id"), nullable=True),
        sa.Column("habit_id", sa.UUID(as_uuid=True), sa.ForeignKey("habits.id"), nullable=True),
        sa.Column("reflection_id", sa.UUID(as_uuid=True), sa.ForeignKey("reflections.id"), nullable=True),
        sa.Column("commitment_id", sa.UUID(as_uuid=True), sa.ForeignKey("commitments.id"), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=32), nullable=False, server_default="aipal"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in (
        "user_id",
        "type",
        "start_time",
        "due_at",
        "status",
        "goal_id",
        "task_id",
        "calendar_event_id",
        "reminder_id",
        "habit_id",
        "reflection_id",
        "commitment_id",
    ):
        op.create_index(f"ix_today_items_{column}", "today_items", [column])

    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("today_item_id", sa.UUID(as_uuid=True), sa.ForeignKey("today_items.id"), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("user_id", "today_item_id", "type", "channel", "scheduled_for", "status"):
        op.create_index(f"ix_notifications_{column}", "notifications", [column])

    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("in_app_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("push_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("reminder_lead_minutes", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("meeting_lead_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("quiet_hours_start", sa.String(length=16), nullable=True),
        sa.Column("quiet_hours_end", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_notification_preferences_user_id", "notification_preferences", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_notification_preferences_user_id", table_name="notification_preferences")
    op.drop_table("notification_preferences")
    for column in ("status", "scheduled_for", "channel", "type", "today_item_id", "user_id"):
        op.drop_index(f"ix_notifications_{column}", table_name="notifications")
    op.drop_table("notifications")
    for column in (
        "commitment_id",
        "reflection_id",
        "habit_id",
        "reminder_id",
        "calendar_event_id",
        "task_id",
        "goal_id",
        "status",
        "due_at",
        "start_time",
        "type",
        "user_id",
    ):
        op.drop_index(f"ix_today_items_{column}", table_name="today_items")
    op.drop_table("today_items")
