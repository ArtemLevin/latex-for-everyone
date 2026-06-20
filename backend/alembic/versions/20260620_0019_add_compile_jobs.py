"""Add compile jobs.

Revision ID: 20260620_0019
Revises: 20260620_0018
Create Date: 2026-06-20
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260620_0019"
down_revision: str | None = "20260620_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "compile_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.String(length=255), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("compile_history_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("stage", sa.String(length=50), nullable=False),
        sa.Column("main_file_name", sa.String(length=255), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("pdf_artifact_id", sa.String(length=36), nullable=True),
        sa.Column("worker_id", sa.String(length=255), nullable=True),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("queued_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["compile_history_id"], ["compile_history.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_compile_jobs_owner_id", "compile_jobs", ["owner_id"])
    op.create_index("ix_compile_jobs_project_id", "compile_jobs", ["project_id"])
    op.create_index("ix_compile_jobs_compile_history_id", "compile_jobs", ["compile_history_id"])
    op.create_index("ix_compile_jobs_status", "compile_jobs", ["status"])
    op.create_index("ix_compile_jobs_stage", "compile_jobs", ["stage"])
    op.create_index("ix_compile_jobs_pdf_artifact_id", "compile_jobs", ["pdf_artifact_id"])
    op.create_index("ix_compile_jobs_worker_id", "compile_jobs", ["worker_id"])
    op.create_index("ix_compile_jobs_locked_at", "compile_jobs", ["locked_at"])
    op.create_index("ix_compile_jobs_heartbeat_at", "compile_jobs", ["heartbeat_at"])
    op.create_index("ix_compile_jobs_queued_at", "compile_jobs", ["queued_at"])
    op.create_index("ix_compile_jobs_created_at", "compile_jobs", ["created_at"])
    op.create_index("ix_compile_jobs_queue_claim", "compile_jobs", ["status", "queued_at"])


def downgrade() -> None:
    op.drop_index("ix_compile_jobs_queue_claim", table_name="compile_jobs")
    op.drop_index("ix_compile_jobs_created_at", table_name="compile_jobs")
    op.drop_index("ix_compile_jobs_queued_at", table_name="compile_jobs")
    op.drop_index("ix_compile_jobs_heartbeat_at", table_name="compile_jobs")
    op.drop_index("ix_compile_jobs_locked_at", table_name="compile_jobs")
    op.drop_index("ix_compile_jobs_worker_id", table_name="compile_jobs")
    op.drop_index("ix_compile_jobs_pdf_artifact_id", table_name="compile_jobs")
    op.drop_index("ix_compile_jobs_stage", table_name="compile_jobs")
    op.drop_index("ix_compile_jobs_status", table_name="compile_jobs")
    op.drop_index("ix_compile_jobs_compile_history_id", table_name="compile_jobs")
    op.drop_index("ix_compile_jobs_project_id", table_name="compile_jobs")
    op.drop_index("ix_compile_jobs_owner_id", table_name="compile_jobs")
    op.drop_table("compile_jobs")
