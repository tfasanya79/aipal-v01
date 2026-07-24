"""Add updated_at columns to users and tasks.

Revision ID: 20260622_0003_user_task_updated_at
Revises: 20260622_0002_goal_reflection_linking
Create Date: 2026-06-22 01:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260622_0003_user_task_updated_at"
down_revision = "20260622_0002_goal_reflection_linking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    task_columns = {column["name"] for column in inspector.get_columns("tasks")}

    if "updated_at" not in user_columns:
        with op.batch_alter_table("users") as batch:
            batch.add_column(
                sa.Column(
                    "updated_at",
                    sa.DateTime(timezone=True),
                    nullable=False,
                    server_default=sa.text("CURRENT_TIMESTAMP"),
                )
            )
    if "updated_at" not in task_columns:
        with op.batch_alter_table("tasks") as batch:
            batch.add_column(
                sa.Column(
                    "updated_at",
                    sa.DateTime(timezone=True),
                    nullable=False,
                    server_default=sa.text("CURRENT_TIMESTAMP"),
                )
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    task_columns = {column["name"] for column in inspector.get_columns("tasks")}
    user_columns = {column["name"] for column in inspector.get_columns("users")}

    if "updated_at" in task_columns:
        with op.batch_alter_table("tasks") as batch:
            batch.drop_column("updated_at")
    if "updated_at" in user_columns:
        with op.batch_alter_table("users") as batch:
            batch.drop_column("updated_at")
