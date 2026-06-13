"""Add lesson transcript review metadata.

Revision ID: 20260613_0011
Revises: 20260613_0010
Create Date: 2026-06-13
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260613_0011"
down_revision: str | None = "20260613_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("lesson_transcripts", sa.Column("edited_text", sa.Text(), nullable=True))
    op.add_column("lesson_transcripts", sa.Column("review_status", sa.String(length=50), nullable=False, server_default="unreviewed"))
    op.add_column("lesson_transcripts", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    op.create_index(op.f("ix_lesson_transcripts_review_status"), "lesson_transcripts", ["review_status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_lesson_transcripts_review_status"), table_name="lesson_transcripts")
    op.drop_column("lesson_transcripts", "reviewed_at")
    op.drop_column("lesson_transcripts", "review_status")
    op.drop_column("lesson_transcripts", "edited_text")
