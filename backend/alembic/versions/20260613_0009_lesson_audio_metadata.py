"""Add lesson audio upload metadata.

Revision ID: 20260613_0009
Revises: 20260612_0008
Create Date: 2026-06-13
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260613_0009"
down_revision: str | None = "20260612_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("lesson_audio_recordings", sa.Column("sha256_checksum", sa.String(length=64), nullable=True))
    op.create_index(
        op.f("ix_lesson_audio_recordings_sha256_checksum"),
        "lesson_audio_recordings",
        ["sha256_checksum"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_lesson_audio_recordings_sha256_checksum"), table_name="lesson_audio_recordings")
    op.drop_column("lesson_audio_recordings", "sha256_checksum")
