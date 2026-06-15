"""Add lesson document provenance metadata.

Revision ID: 20260615_0013
Revises: 20260615_0012
Create Date: 2026-06-15
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260615_0013"
down_revision: str | None = "20260615_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("lesson_generated_documents", sa.Column("provider", sa.String(length=100), nullable=False, server_default="unknown"))
    op.add_column("lesson_generated_documents", sa.Column("prompt_template_hash", sa.String(length=64), nullable=True))
    op.add_column("lesson_generated_documents", sa.Column("source_text_hash", sa.String(length=64), nullable=True))
    op.add_column("lesson_generated_documents", sa.Column("source_text_kind", sa.String(length=50), nullable=False, server_default="raw"))


def downgrade() -> None:
    op.drop_column("lesson_generated_documents", "source_text_kind")
    op.drop_column("lesson_generated_documents", "source_text_hash")
    op.drop_column("lesson_generated_documents", "prompt_template_hash")
    op.drop_column("lesson_generated_documents", "provider")
