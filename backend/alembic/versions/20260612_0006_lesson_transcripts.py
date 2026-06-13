"""Add lesson transcript metadata.

Revision ID: 20260612_0006
Revises: 20260612_0005
Create Date: 2026-06-12
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260612_0006"
down_revision: str | None = "20260612_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lesson_transcripts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("lesson_id", sa.String(length=36), nullable=False),
        sa.Column("recording_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"]),
        sa.ForeignKeyConstraint(["recording_id"], ["lesson_audio_recordings.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_lesson_transcripts_lesson_id"), "lesson_transcripts", ["lesson_id"], unique=False)
    op.create_index(op.f("ix_lesson_transcripts_recording_id"), "lesson_transcripts", ["recording_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_lesson_transcripts_recording_id"), table_name="lesson_transcripts")
    op.drop_index(op.f("ix_lesson_transcripts_lesson_id"), table_name="lesson_transcripts")
    op.drop_table("lesson_transcripts")
