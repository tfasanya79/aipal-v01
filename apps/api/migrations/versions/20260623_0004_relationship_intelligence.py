"""relationship intelligence

Revision ID: 20260623_0004_relationship_intelligence
Revises: 20260622_0003_user_task_updated_at
Create Date: 2026-06-23 00:04:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260623_0004_relationship_intelligence"
down_revision = "20260622_0003_user_task_updated_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("memories") as batch:
        batch.add_column(sa.Column("follow_up_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("follow_up_status", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("follow_up_prompt", sa.Text(), nullable=True))
        batch.add_column(sa.Column("event_date", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("entities", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("sentiment", sa.String(length=32), nullable=True))

    with op.batch_alter_table("reflections") as batch:
        batch.add_column(sa.Column("summary", sa.Text(), nullable=True))
        batch.add_column(sa.Column("metadata", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("score", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("reflections") as batch:
        batch.drop_column("score")
        batch.drop_column("metadata")
        batch.drop_column("summary")

    with op.batch_alter_table("memories") as batch:
        batch.drop_column("sentiment")
        batch.drop_column("entities")
        batch.drop_column("event_date")
        batch.drop_column("follow_up_prompt")
        batch.drop_column("follow_up_status")
        batch.drop_column("follow_up_at")
