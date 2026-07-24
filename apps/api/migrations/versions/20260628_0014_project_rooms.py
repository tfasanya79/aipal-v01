"""project rooms

Revision ID: 20260628_0014_project_rooms
Revises: 20260627_0013_meeting_assistant
Create Date: 2026-06-28 09:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260628_0014_project_rooms"
down_revision = "20260627_0013_meeting_assistant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_rooms",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("business_project_id", sa.UUID(as_uuid=True), sa.ForeignKey("business_projects.id"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("goals", sa.JSON(), nullable=True),
        sa.Column("key_people", sa.JSON(), nullable=True),
        sa.Column("risks", sa.JSON(), nullable=True),
        sa.Column("opportunities", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("user_id", "business_project_id", "status"):
        op.create_index(f"ix_project_rooms_{column}", "project_rooms", [column])

    op.create_table(
        "project_room_links",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("room_id", sa.UUID(as_uuid=True), sa.ForeignKey("project_rooms.id"), nullable=False),
        sa.Column("linked_type", sa.String(length=64), nullable=False),
        sa.Column("linked_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("user_id", "room_id", "linked_type", "linked_id"):
        op.create_index(f"ix_project_room_links_{column}", "project_room_links", [column])

    op.execute(
        """
        INSERT INTO project_rooms (
            id, user_id, business_project_id, name, description, status,
            goals, key_people, risks, opportunities, metadata, created_at, updated_at
        )
        SELECT
            id, user_id, id, name, description, status,
            goals, key_people, risks, opportunities, NULL, created_at, updated_at
        FROM business_projects
        """
    )


def downgrade() -> None:
    for column in ("linked_id", "linked_type", "room_id", "user_id"):
        op.drop_index(f"ix_project_room_links_{column}", table_name="project_room_links")
    op.drop_table("project_room_links")
    for column in ("status", "business_project_id", "user_id"):
        op.drop_index(f"ix_project_rooms_{column}", table_name="project_rooms")
    op.drop_table("project_rooms")
