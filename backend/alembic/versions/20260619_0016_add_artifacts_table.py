"""Add owner-scoped artifacts table.

Revision ID: 20260619_0016
Revises: 20260615_0015
Create Date: 2026-06-19
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260619_0016"
down_revision: str | None = "20260615_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=255), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("compile_history_id", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("format", sa.String(length=20), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_root", sa.String(length=50), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("content_disposition_type", sa.String(length=30), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256_checksum", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("accessed_at", sa.DateTime(), nullable=True),
        sa.Column("access_count", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["compile_history_id"], ["compile_history.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_filename", name="uq_artifacts_storage_filename"),
    )
    op.create_index("ix_artifacts_owner_id", "artifacts", ["owner_id"])
    op.create_index("ix_artifacts_project_id", "artifacts", ["project_id"])
    op.create_index("ix_artifacts_compile_history_id", "artifacts", ["compile_history_id"])
    op.create_index("ix_artifacts_kind", "artifacts", ["kind"])
    op.create_index("ix_artifacts_status", "artifacts", ["status"])
    op.create_index("ix_artifacts_expires_at", "artifacts", ["expires_at"])
    op.create_index("ix_artifacts_storage_filename", "artifacts", ["storage_filename"])
    op.create_index("ix_artifacts_owner_created", "artifacts", ["owner_id", "created_at"])
    op.create_index("ix_artifacts_owner_project", "artifacts", ["owner_id", "project_id"])
    op.create_index("ix_artifacts_owner_storage", "artifacts", ["owner_id", "storage_filename"])


def downgrade() -> None:
    op.drop_index("ix_artifacts_owner_storage", table_name="artifacts")
    op.drop_index("ix_artifacts_owner_project", table_name="artifacts")
    op.drop_index("ix_artifacts_owner_created", table_name="artifacts")
    op.drop_index("ix_artifacts_storage_filename", table_name="artifacts")
    op.drop_index("ix_artifacts_expires_at", table_name="artifacts")
    op.drop_index("ix_artifacts_status", table_name="artifacts")
    op.drop_index("ix_artifacts_kind", table_name="artifacts")
    op.drop_index("ix_artifacts_compile_history_id", table_name="artifacts")
    op.drop_index("ix_artifacts_project_id", table_name="artifacts")
    op.drop_index("ix_artifacts_owner_id", table_name="artifacts")
    op.drop_table("artifacts")
