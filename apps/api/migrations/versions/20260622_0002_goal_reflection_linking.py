"""Add goal and reflection linking for companion detail views.

Revision ID: 20260622_0002_goal_reflection_linking
Revises: 20260622_0001_companion_phase1
Create Date: 2026-06-22 00:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260622_0002_goal_reflection_linking"
down_revision = "20260622_0001_companion_phase1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("goal_id", sa.Uuid(as_uuid=True), nullable=True))
        batch.create_foreign_key("fk_tasks_goal_id_goals", "goals", ["goal_id"], ["id"])
    op.create_index("ix_tasks_goal_id", "tasks", ["goal_id"])

    with op.batch_alter_table("reflections") as batch:
        batch.add_column(sa.Column("goal_id", sa.Uuid(as_uuid=True), nullable=True))
        batch.create_foreign_key("fk_reflections_goal_id_goals", "goals", ["goal_id"], ["id"])
    op.create_index("ix_reflections_goal_id", "reflections", ["goal_id"])


def downgrade() -> None:
    op.drop_index("ix_reflections_goal_id", table_name="reflections")
    with op.batch_alter_table("reflections") as batch:
        batch.drop_constraint("fk_reflections_goal_id_goals", type_="foreignkey")
        batch.drop_column("goal_id")

    op.drop_index("ix_tasks_goal_id", table_name="tasks")
    with op.batch_alter_table("tasks") as batch:
        batch.drop_constraint("fk_tasks_goal_id_goals", type_="foreignkey")
        batch.drop_column("goal_id")
