"""memory confidence layer

Revision ID: 20260623_0007_memory_confidence_layer
Revises: 20260623_0006_phase45_companion_os
Create Date: 2026-06-23 04:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260623_0007_memory_confidence_layer"
down_revision = "20260623_0006_phase45_companion_os"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("memories") as batch:
        batch.add_column(sa.Column("approval_status", sa.String(length=32), nullable=False, server_default="approved"))
        batch.add_column(sa.Column("memory_scope", sa.String(length=32), nullable=False, server_default="permanent"))
        batch.add_column(sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("suggested_reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("edited_from_id", sa.UUID(as_uuid=True), nullable=True))
        batch.create_foreign_key(
            "fk_memories_edited_from_id",
            "memories",
            ["edited_from_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("memories") as batch:
        batch.drop_constraint("fk_memories_edited_from_id", type_="foreignkey")
        batch.drop_column("edited_from_id")
        batch.drop_column("suggested_reason")
        batch.drop_column("expires_at")
        batch.drop_column("memory_scope")
        batch.drop_column("approval_status")
