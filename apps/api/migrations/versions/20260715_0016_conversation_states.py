"""Add durable canonical conversation state.

Revision ID: 20260715_0016_conversation_states
Revises: 20260628_0015_focus_sessions
Create Date: 2026-07-15 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260715_0016_conversation_states"
down_revision = "20260628_0015_focus_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_states",
        sa.Column(
            "conversation_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state_json", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_conversation_states_user_id", "conversation_states", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_conversation_states_user_id", table_name="conversation_states")
    op.drop_table("conversation_states")
