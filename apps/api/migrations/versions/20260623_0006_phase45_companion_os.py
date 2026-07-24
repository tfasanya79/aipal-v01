"""phase 4 and 5 companion os

Revision ID: 20260623_0006_phase45_companion_os
Revises: 20260623_0005_phase3_coaching
Create Date: 2026-06-23 03:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260623_0006_phase45_companion_os"
down_revision = "20260623_0005_phase3_coaching"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("memories") as batch:
        batch.add_column(sa.Column("source_provider", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("source_item_id", sa.UUID(as_uuid=True), nullable=True))

    op.create_table(
        "user_companion_preferences",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("proactive_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("max_proactive_per_day", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("quiet_hours_start", sa.String(length=16), nullable=True),
        sa.Column("quiet_hours_end", sa.String(length=16), nullable=True),
        sa.Column("tone", sa.String(length=32), nullable=False, server_default="warm"),
        sa.Column("humor_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("directness_level", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("voice_pace", sa.String(length=16), nullable=False, server_default="normal"),
        sa.Column("response_length", sa.String(length=16), nullable=False, server_default="balanced"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_companion_preferences_user_id", "user_companion_preferences", ["user_id"], unique=True)

    op.create_table(
        "proactive_prompts",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("trigger_type", sa.String(length=64), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("source_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_proactive_prompts_user_id", "proactive_prompts", ["user_id"])

    op.create_table(
        "emotional_patterns",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("pattern_type", sa.String(length=64), nullable=False),
        sa.Column("emotion", sa.String(length=32), nullable=False),
        sa.Column("life_area", sa.String(length=32), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=False, server_default="0.50"),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_emotional_patterns_user_id", "emotional_patterns", ["user_id"])

    op.create_table(
        "connected_accounts",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("account_label", sa.String(length=255), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("access_token_encrypted", sa.Text(), nullable=True),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_connected_accounts_user_id", "connected_accounts", ["user_id"])

    op.create_table(
        "connected_items",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("connected_account_id", sa.UUID(as_uuid=True), sa.ForeignKey("connected_accounts.id"), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("item_type", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content_summary", sa.Text(), nullable=True),
        sa.Column("source_metadata", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_connected_items_user_id", "connected_items", ["user_id"])
    op.create_index("ix_connected_items_connected_account_id", "connected_items", ["connected_account_id"])
    op.create_index("ix_connected_items_provider", "connected_items", ["provider"])

    op.create_table(
        "external_commitments",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_provider", sa.String(length=64), nullable=False),
        sa.Column("source_item_id", sa.UUID(as_uuid=True), sa.ForeignKey("connected_items.id"), nullable=False),
        sa.Column("commitment_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=False, server_default="0.50"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_external_commitments_user_id", "external_commitments", ["user_id"])
    op.create_index("ix_external_commitments_source_item_id", "external_commitments", ["source_item_id"])

    op.create_table(
        "connector_audit_logs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_connector_audit_logs_user_id", "connector_audit_logs", ["user_id"])

    op.create_table(
        "business_projects",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("goals", sa.JSON(), nullable=True),
        sa.Column("key_people", sa.JSON(), nullable=True),
        sa.Column("risks", sa.JSON(), nullable=True),
        sa.Column("opportunities", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_business_projects_user_id", "business_projects", ["user_id"])

    op.create_table(
        "business_project_events",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), sa.ForeignKey("business_projects.id"), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("source_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_business_project_events_user_id", "business_project_events", ["user_id"])
    op.create_index("ix_business_project_events_project_id", "business_project_events", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_business_project_events_project_id", table_name="business_project_events")
    op.drop_index("ix_business_project_events_user_id", table_name="business_project_events")
    op.drop_table("business_project_events")

    op.drop_index("ix_business_projects_user_id", table_name="business_projects")
    op.drop_table("business_projects")

    op.drop_index("ix_connector_audit_logs_user_id", table_name="connector_audit_logs")
    op.drop_table("connector_audit_logs")

    op.drop_index("ix_external_commitments_source_item_id", table_name="external_commitments")
    op.drop_index("ix_external_commitments_user_id", table_name="external_commitments")
    op.drop_table("external_commitments")

    op.drop_index("ix_connected_items_provider", table_name="connected_items")
    op.drop_index("ix_connected_items_connected_account_id", table_name="connected_items")
    op.drop_index("ix_connected_items_user_id", table_name="connected_items")
    op.drop_table("connected_items")

    op.drop_index("ix_connected_accounts_user_id", table_name="connected_accounts")
    op.drop_table("connected_accounts")

    op.drop_index("ix_emotional_patterns_user_id", table_name="emotional_patterns")
    op.drop_table("emotional_patterns")

    op.drop_index("ix_proactive_prompts_user_id", table_name="proactive_prompts")
    op.drop_table("proactive_prompts")

    op.drop_index("ix_user_companion_preferences_user_id", table_name="user_companion_preferences")
    op.drop_table("user_companion_preferences")

    with op.batch_alter_table("memories") as batch:
        batch.drop_column("source_item_id")
        batch.drop_column("source_provider")
