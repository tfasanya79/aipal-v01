"""Phase 5 unified semantic memory index.

Revision ID: 20260715_0017_phase5_memory_index
Revises: 20260715_0016_conversation_states
"""

from alembic import op
import sqlalchemy as sa

from app.models import Vector1536


revision = "20260715_0017_phase5_memory_index"
down_revision = "20260715_0016_conversation_states"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "messages",
        sa.Column("source", sa.String(32), nullable=False, server_default="text"),
    )
    op.create_table(
        "memory_search_documents",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("embedding", Vector1536(), nullable=False),
        sa.Column("bucket_0", sa.String(16), nullable=False),
        sa.Column("bucket_1", sa.String(16), nullable=False),
        sa.Column("bucket_2", sa.String(16), nullable=False),
        sa.Column("bucket_3", sa.String(16), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "source_type", "source_id", name="uq_memory_search_source"),
    )
    for column in ("user_id", "source_type", "bucket_0", "bucket_1", "bucket_2", "bucket_3", "source_updated_at"):
        op.create_index(f"ix_memory_search_documents_{column}", "memory_search_documents", [column])
    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_memory_search_documents_embedding_hnsw "
            "ON memory_search_documents USING hnsw (embedding vector_cosine_ops)"
        )
    op.create_table(
        "memory_index_status",
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("memory_index_status")
    op.drop_table("memory_search_documents")
    op.drop_column("messages", "source")
