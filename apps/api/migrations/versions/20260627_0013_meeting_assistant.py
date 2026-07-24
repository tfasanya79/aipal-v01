"""meeting assistant

Revision ID: 20260627_0013_meeting_assistant
Revises: 20260627_0012_proactive_prompt_metadata
Create Date: 2026-06-27 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260627_0013_meeting_assistant"
down_revision = "20260627_0012_proactive_prompt_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meetings",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("participants", sa.JSON(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("meeting_link", sa.Text(), nullable=True),
        sa.Column("project_id", sa.UUID(as_uuid=True), sa.ForeignKey("business_projects.id"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="scheduled"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("user_id", "start_time", "project_id", "status"):
        op.create_index(f"ix_meetings_{column}", "meetings", [column])

    op.create_table(
        "meeting_notes",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("meeting_id", sa.UUID(as_uuid=True), sa.ForeignKey("meetings.id"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("decisions", sa.JSON(), nullable=True),
        sa.Column("action_items", sa.JSON(), nullable=True),
        sa.Column("followups", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("user_id", "meeting_id"):
        op.create_index(f"ix_meeting_notes_{column}", "meeting_notes", [column])


def downgrade() -> None:
    for column in ("meeting_id", "user_id"):
        op.drop_index(f"ix_meeting_notes_{column}", table_name="meeting_notes")
    op.drop_table("meeting_notes")
    for column in ("status", "project_id", "start_time", "user_id"):
        op.drop_index(f"ix_meetings_{column}", table_name="meetings")
    op.drop_table("meetings")
