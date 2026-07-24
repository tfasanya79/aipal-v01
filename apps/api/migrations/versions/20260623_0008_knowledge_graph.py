"""knowledge graph

Revision ID: 20260623_0008_knowledge_graph
Revises: 20260623_0007_memory_confidence_layer
Create Date: 2026-06-23 05:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260623_0008_knowledge_graph"
down_revision = "20260623_0007_memory_confidence_layer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_entities",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=False, server_default="0.50"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_knowledge_entities_user_id", "knowledge_entities", ["user_id"])
    op.create_index("ix_knowledge_entities_entity_type", "knowledge_entities", ["entity_type"])
    op.create_index("ix_knowledge_entities_name", "knowledge_entities", ["name"])

    op.create_table(
        "knowledge_edges",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_entity_id", sa.UUID(as_uuid=True), sa.ForeignKey("knowledge_entities.id"), nullable=False),
        sa.Column("target_entity_id", sa.UUID(as_uuid=True), sa.ForeignKey("knowledge_entities.id"), nullable=False),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column("weight", sa.Numeric(5, 2), nullable=False, server_default="1"),
        sa.Column("evidence_memory_id", sa.UUID(as_uuid=True), sa.ForeignKey("memories.id"), nullable=True),
        sa.Column("evidence_message_id", sa.UUID(as_uuid=True), sa.ForeignKey("messages.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_knowledge_edges_user_id", "knowledge_edges", ["user_id"])
    op.create_index("ix_knowledge_edges_source_entity_id", "knowledge_edges", ["source_entity_id"])
    op.create_index("ix_knowledge_edges_target_entity_id", "knowledge_edges", ["target_entity_id"])
    op.create_index("ix_knowledge_edges_relation_type", "knowledge_edges", ["relation_type"])
    op.create_index("ix_knowledge_edges_evidence_memory_id", "knowledge_edges", ["evidence_memory_id"])
    op.create_index("ix_knowledge_edges_evidence_message_id", "knowledge_edges", ["evidence_message_id"])

    op.create_table(
        "memory_entity_links",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("memory_id", sa.UUID(as_uuid=True), sa.ForeignKey("memories.id"), nullable=False),
        sa.Column("entity_id", sa.UUID(as_uuid=True), sa.ForeignKey("knowledge_entities.id"), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=False, server_default="0.50"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_memory_entity_links_user_id", "memory_entity_links", ["user_id"])
    op.create_index("ix_memory_entity_links_memory_id", "memory_entity_links", ["memory_id"])
    op.create_index("ix_memory_entity_links_entity_id", "memory_entity_links", ["entity_id"])


def downgrade() -> None:
    op.drop_index("ix_memory_entity_links_entity_id", table_name="memory_entity_links")
    op.drop_index("ix_memory_entity_links_memory_id", table_name="memory_entity_links")
    op.drop_index("ix_memory_entity_links_user_id", table_name="memory_entity_links")
    op.drop_table("memory_entity_links")

    op.drop_index("ix_knowledge_edges_evidence_message_id", table_name="knowledge_edges")
    op.drop_index("ix_knowledge_edges_evidence_memory_id", table_name="knowledge_edges")
    op.drop_index("ix_knowledge_edges_relation_type", table_name="knowledge_edges")
    op.drop_index("ix_knowledge_edges_target_entity_id", table_name="knowledge_edges")
    op.drop_index("ix_knowledge_edges_source_entity_id", table_name="knowledge_edges")
    op.drop_index("ix_knowledge_edges_user_id", table_name="knowledge_edges")
    op.drop_table("knowledge_edges")

    op.drop_index("ix_knowledge_entities_name", table_name="knowledge_entities")
    op.drop_index("ix_knowledge_entities_entity_type", table_name="knowledge_entities")
    op.drop_index("ix_knowledge_entities_user_id", table_name="knowledge_entities")
    op.drop_table("knowledge_entities")
