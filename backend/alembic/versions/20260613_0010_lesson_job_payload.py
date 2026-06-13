"""Add lesson processing job payload metadata.

Revision ID: 20260613_0010
Revises: 20260613_0009
Create Date: 2026-06-13
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260613_0010"
down_revision: str | None = "20260613_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("lesson_processing_jobs", sa.Column("document_types", sa.JSON(), nullable=True))
    op.execute("UPDATE lesson_processing_jobs SET document_types = '[]' WHERE document_types IS NULL")


def downgrade() -> None:
    op.drop_column("lesson_processing_jobs", "document_types")
