"""Add generation job worker locking fields.

Revision ID: 20260619_0017
Revises: 20260619_0016
Create Date: 2026-06-19
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260619_0017"
down_revision: str | None = "20260619_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("generation_jobs", sa.Column("worker_id", sa.String(length=255), nullable=True))
    op.add_column("generation_jobs", sa.Column("locked_at", sa.DateTime(), nullable=True))
    op.add_column("generation_jobs", sa.Column("heartbeat_at", sa.DateTime(), nullable=True))
    op.add_column("generation_jobs", sa.Column("next_attempt_at", sa.DateTime(), nullable=True))
    op.create_index("ix_generation_jobs_worker_id", "generation_jobs", ["worker_id"])
    op.create_index("ix_generation_jobs_locked_at", "generation_jobs", ["locked_at"])
    op.create_index("ix_generation_jobs_heartbeat_at", "generation_jobs", ["heartbeat_at"])
    op.create_index("ix_generation_jobs_next_attempt_at", "generation_jobs", ["next_attempt_at"])
    op.create_index("ix_generation_jobs_queue_claim", "generation_jobs", ["status", "next_attempt_at", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_generation_jobs_queue_claim", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_next_attempt_at", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_heartbeat_at", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_locked_at", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_worker_id", table_name="generation_jobs")
    op.drop_column("generation_jobs", "next_attempt_at")
    op.drop_column("generation_jobs", "heartbeat_at")
    op.drop_column("generation_jobs", "locked_at")
    op.drop_column("generation_jobs", "worker_id")
