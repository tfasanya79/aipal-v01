"""focus sessions

Revision ID: 20260628_0015_focus_sessions
Revises: 20260628_0014_project_rooms
Create Date: 2026-06-28 11:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260628_0015_focus_sessions"
down_revision = "20260628_0014_project_rooms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "focus_sessions",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("today_item_id", sa.UUID(as_uuid=True), sa.ForeignKey("today_items.id"), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("reflection_prompt", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("user_id", "today_item_id", "status"):
        op.create_index(f"ix_focus_sessions_{column}", "focus_sessions", [column])


def downgrade() -> None:
    for column in ("status", "today_item_id", "user_id"):
        op.drop_index(f"ix_focus_sessions_{column}", table_name="focus_sessions")
    op.drop_table("focus_sessions")
