"""Add pupil and lesson domain foundation.

Revision ID: 20260609_0004
Revises: 20260607_0003
Create Date: 2026-06-09
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260609_0004"
down_revision: str | None = "20260607_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pupils",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("teacher_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pupils_teacher_id"), "pupils", ["teacher_id"], unique=False)

    op.create_table(
        "lessons",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pupil_id", sa.String(length=36), nullable=False),
        sa.Column("teacher_id", sa.String(length=255), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("lesson_date", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["pupil_id"], ["pupils.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_lessons_lesson_date"), "lessons", ["lesson_date"], unique=False)
    op.create_index(op.f("ix_lessons_pupil_id"), "lessons", ["pupil_id"], unique=False)
    op.create_index(op.f("ix_lessons_teacher_id"), "lessons", ["teacher_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_lessons_teacher_id"), table_name="lessons")
    op.drop_index(op.f("ix_lessons_pupil_id"), table_name="lessons")
    op.drop_index(op.f("ix_lessons_lesson_date"), table_name="lessons")
    op.drop_table("lessons")
    op.drop_index(op.f("ix_pupils_teacher_id"), table_name="pupils")
    op.drop_table("pupils")
