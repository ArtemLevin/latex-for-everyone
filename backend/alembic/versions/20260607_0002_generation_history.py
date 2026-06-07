"""Add AI generation history table.

Revision ID: 20260607_0002
Revises: 20260606_0001
Create Date: 2026-06-07
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260607_0002"
down_revision: str | None = "20260606_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "generation_history",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("prompt_preview", sa.Text(), nullable=True),
        sa.Column("raw_output_hash", sa.String(length=64), nullable=True),
        sa.Column("latex_code_hash", sa.String(length=64), nullable=True),
        sa.Column("latex_code_preview", sa.Text(), nullable=True),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("validation", sa.JSON(), nullable=True),
        sa.Column("compile_check", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_generation_history_project_id"), "generation_history", ["project_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_generation_history_project_id"), table_name="generation_history")
    op.drop_table("generation_history")
