"""Add generation job idempotency key.

Revision ID: 20260615_0015
Revises: 20260615_0014
Create Date: 2026-06-15
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260615_0015"
down_revision: str | None = "20260615_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("generation_jobs", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.create_index("ix_generation_jobs_idempotency_key", "generation_jobs", ["idempotency_key"])


def downgrade() -> None:
    op.drop_index("ix_generation_jobs_idempotency_key", table_name="generation_jobs")
    op.drop_column("generation_jobs", "idempotency_key")
