"""Phase 1 companion foundation.

Revision ID: 20260622_0001_companion_phase1
Revises: 
Create Date: 2026-06-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

from app.models import Vector1536


revision = "20260622_0001_companion_phase1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Several historical revision identifiers exceed Alembic's default
        # VARCHAR(32). Widen the version table before Alembic records revision
        # 0002 so a clean PostgreSQL migration can advance through the chain.
        op.alter_column(
            "alembic_version",
            "version_num",
            existing_type=sa.String(length=32),
            type_=sa.String(length=128),
            existing_nullable=False,
        )
    inspector = sa.inspect(bind)

    if not inspector.has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
            sa.Column("email", sa.String(length=320), nullable=False, unique=True),
            sa.Column("display_name", sa.String(length=120), nullable=True),
            sa.Column("wake_name", sa.String(length=120), nullable=True),
            sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
            sa.Column("about_me", sa.Text(), nullable=True),
            sa.Column("morning_brief_at", sa.Time(), nullable=True),
            sa.Column("evening_recap_at", sa.Time(), nullable=True),
            sa.Column("checkin_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not inspector.has_table("tasks"):
        op.create_table(
            "tasks",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("title", sa.String(length=500), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("priority", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("source", sa.String(length=32), nullable=False),
            sa.Column("parent_task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=True),
            sa.Column("estimated_minutes", sa.Integer(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.Column("category", sa.String(length=32), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )

    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("strengths", sa.JSON(), nullable=True),
        sa.Column("challenges", sa.JSON(), nullable=True),
        sa.Column("preferences", sa.JSON(), nullable=True),
        sa.Column("life_areas", sa.JSON(), nullable=True),
        sa.Column("current_projects", sa.JSON(), nullable=True),
        sa.Column("current_goals", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", sa.Uuid(as_uuid=True), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("emotion", sa.String(length=32), nullable=True),
        sa.Column("intent", sa.String(length=32), nullable=True),
        sa.Column("mode", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "memories",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("life_area", sa.String(length=32), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("importance", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_message_id", sa.Uuid(as_uuid=True), sa.ForeignKey("messages.id"), nullable=True),
        sa.Column("embedding", Vector1536(), nullable=True),
        sa.Column("sensitive", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("user_approved", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "goals",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("life_area", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "emotional_states",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("message_id", sa.Uuid(as_uuid=True), sa.ForeignKey("messages.id"), nullable=True),
        sa.Column("emotion", sa.String(length=32), nullable=False),
        sa.Column("intensity", sa.Integer(), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "reflections",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("wins", sa.Text(), nullable=True),
        sa.Column("challenges", sa.Text(), nullable=True),
        sa.Column("lessons", sa.Text(), nullable=True),
        sa.Column("mood", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "reminders",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("remind_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recurrence_rule", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("reminders")
    op.drop_table("reflections")
    op.drop_table("emotional_states")
    op.drop_table("goals")
    op.drop_table("memories")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("user_profiles")
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("tasks"):
        op.drop_table("tasks")
    if inspector.has_table("users"):
        op.drop_table("users")
