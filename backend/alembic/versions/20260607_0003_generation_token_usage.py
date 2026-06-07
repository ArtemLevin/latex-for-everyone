"""Add AI generation token usage fields.

Revision ID: 20260607_0003
Revises: 20260607_0002
Create Date: 2026-06-07
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260607_0003"
down_revision: str | None = "20260607_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("generation_history", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("generation_history", sa.Column("output_tokens", sa.Integer(), nullable=True))
    op.add_column("generation_history", sa.Column("total_tokens", sa.Integer(), nullable=True))
    op.add_column("generation_history", sa.Column("token_count_source", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("generation_history", "token_count_source")
    op.drop_column("generation_history", "total_tokens")
    op.drop_column("generation_history", "output_tokens")
    op.drop_column("generation_history", "input_tokens")
