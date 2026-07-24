"""commitment tracking

Revision ID: 20260623_0009_commitment_tracking
Revises: 20260623_0008_knowledge_graph
Create Date: 2026-06-23 06:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260623_0009_commitment_tracking"
down_revision = "20260623_0008_knowledge_graph"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commitments",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("source_message_id", sa.UUID(as_uuid=True), sa.ForeignKey("messages.id"), nullable=True),
        sa.Column("source_memory_id", sa.UUID(as_uuid=True), sa.ForeignKey("memories.id"), nullable=True),
        sa.Column("follow_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=False, server_default="0.80"),
        sa.Column("related_entity_id", sa.UUID(as_uuid=True), sa.ForeignKey("knowledge_entities.id"), nullable=True),
        sa.Column("related_entity_type", sa.String(length=32), nullable=True),
        sa.Column("related_entity_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_commitments_user_id", "commitments", ["user_id"])
    op.create_index("ix_commitments_status", "commitments", ["status"])
    op.create_index("ix_commitments_due_at", "commitments", ["due_at"])
    op.create_index("ix_commitments_follow_up_at", "commitments", ["follow_up_at"])
    op.create_index("ix_commitments_related_entity_id", "commitments", ["related_entity_id"])


def downgrade() -> None:
    op.drop_index("ix_commitments_related_entity_id", table_name="commitments")
    op.drop_index("ix_commitments_follow_up_at", table_name="commitments")
    op.drop_index("ix_commitments_due_at", table_name="commitments")
    op.drop_index("ix_commitments_status", table_name="commitments")
    op.drop_index("ix_commitments_user_id", table_name="commitments")
    op.drop_table("commitments")
