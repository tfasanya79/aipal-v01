"""proactive prompt trigger metadata

Revision ID: 20260627_0012_proactive_prompt_metadata
Revises: 20260627_0011_today_items_notifications
Create Date: 2026-06-27 13:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260627_0012_proactive_prompt_metadata"
down_revision = "20260627_0011_today_items_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("proactive_prompts", sa.Column("trigger_metadata", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("proactive_prompts", "trigger_metadata")
