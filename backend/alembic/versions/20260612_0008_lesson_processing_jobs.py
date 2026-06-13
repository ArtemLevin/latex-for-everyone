"""Add lesson processing jobs.

Revision ID: 20260612_0008
Revises: 20260612_0007
Create Date: 2026-06-12
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260612_0008"
down_revision: str | None = "20260612_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lesson_processing_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("lesson_id", sa.String(length=36), nullable=False),
        sa.Column("teacher_id", sa.String(length=255), nullable=False),
        sa.Column("job_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("stage", sa.String(length=50), nullable=False),
        sa.Column("recording_id", sa.String(length=36), nullable=True),
        sa.Column("transcript_id", sa.String(length=36), nullable=True),
        sa.Column("document_ids", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_lesson_processing_jobs_lesson_id"), "lesson_processing_jobs", ["lesson_id"], unique=False)
    op.create_index(op.f("ix_lesson_processing_jobs_teacher_id"), "lesson_processing_jobs", ["teacher_id"], unique=False)
    op.create_index(op.f("ix_lesson_processing_jobs_job_type"), "lesson_processing_jobs", ["job_type"], unique=False)
    op.create_index(op.f("ix_lesson_processing_jobs_status"), "lesson_processing_jobs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_lesson_processing_jobs_status"), table_name="lesson_processing_jobs")
    op.drop_index(op.f("ix_lesson_processing_jobs_job_type"), table_name="lesson_processing_jobs")
    op.drop_index(op.f("ix_lesson_processing_jobs_teacher_id"), table_name="lesson_processing_jobs")
    op.drop_index(op.f("ix_lesson_processing_jobs_lesson_id"), table_name="lesson_processing_jobs")
    op.drop_table("lesson_processing_jobs")
