"""Add owner scope to generation jobs and history.

Revision ID: 20260615_0014
Revises: 20260615_0013
Create Date: 2026-06-15
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260615_0014"
down_revision: str | None = "20260615_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("generation_history", sa.Column("owner_id", sa.String(length=255), nullable=False, server_default="local-teacher"))
    op.add_column("generation_jobs", sa.Column("owner_id", sa.String(length=255), nullable=False, server_default="local-teacher"))
    op.create_index("ix_generation_history_owner_id", "generation_history", ["owner_id"])
    op.create_index("ix_generation_jobs_owner_id", "generation_jobs", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_generation_jobs_owner_id", table_name="generation_jobs")
    op.drop_index("ix_generation_history_owner_id", table_name="generation_history")
    op.drop_column("generation_jobs", "owner_id")
    op.drop_column("generation_history", "owner_id")
