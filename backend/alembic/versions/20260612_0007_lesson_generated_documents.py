"""Add lesson generated document metadata.

Revision ID: 20260612_0007
Revises: 20260612_0006
Create Date: 2026-06-12
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260612_0007"
down_revision: str | None = "20260612_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lesson_generated_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("lesson_id", sa.String(length=36), nullable=False),
        sa.Column("transcript_id", sa.String(length=36), nullable=False),
        sa.Column("document_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"]),
        sa.ForeignKeyConstraint(["transcript_id"], ["lesson_transcripts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_lesson_generated_documents_lesson_id"), "lesson_generated_documents", ["lesson_id"], unique=False)
    op.create_index(op.f("ix_lesson_generated_documents_transcript_id"), "lesson_generated_documents", ["transcript_id"], unique=False)
    op.create_index(op.f("ix_lesson_generated_documents_document_type"), "lesson_generated_documents", ["document_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_lesson_generated_documents_document_type"), table_name="lesson_generated_documents")
    op.drop_index(op.f("ix_lesson_generated_documents_transcript_id"), table_name="lesson_generated_documents")
    op.drop_index(op.f("ix_lesson_generated_documents_lesson_id"), table_name="lesson_generated_documents")
    op.drop_table("lesson_generated_documents")
