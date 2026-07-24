"""companion tts voice preference

Revision ID: 20260626_0010_companion_tts_voice
Revises: 20260623_0009_commitment_tracking
Create Date: 2026-06-26 04:55:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260626_0010_companion_tts_voice"
down_revision = "20260623_0009_commitment_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_companion_preferences",
        sa.Column("tts_voice", sa.String(length=64), nullable=False, server_default="default"),
    )


def downgrade() -> None:
    op.drop_column("user_companion_preferences", "tts_voice")
