"""Add user auth sessions and audit logs.

Revision ID: 20260620_0018
Revises: 20260619_0017
Create Date: 2026-06-20
"""

from collections.abc import Iterable, Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column


revision: str = "20260620_0018"
down_revision: str | None = "20260619_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_has_column(connection, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(connection)
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _collect_legacy_identities(connection) -> set[str]:
    sources: Iterable[tuple[str, str]] = (
        ("projects", "owner_id"),
        ("pupils", "teacher_id"),
        ("lessons", "teacher_id"),
        ("generation_history", "owner_id"),
        ("generation_jobs", "owner_id"),
        ("artifacts", "owner_id"),
    )
    identities: set[str] = set()
    for table_name, column_name in sources:
        if not _table_has_column(connection, table_name, column_name):
            continue
        for (value,) in connection.execute(sa.text(f"SELECT DISTINCT {column_name} FROM {table_name} WHERE {column_name} IS NOT NULL")):
            identity = str(value).strip() if value is not None else ""
            if identity:
                identities.add(identity)
    return identities


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("normalized_email", sa.String(length=320), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("auth_provider", sa.String(length=50), nullable=False, server_default="password"),
        sa.Column("external_subject", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=50), nullable=False, server_default="teacher"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("normalized_email", name="uq_users_normalized_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_normalized_email", "users", ["normalized_email"])
    op.create_index("ix_users_auth_provider", "users", ["auth_provider"])
    op.create_index("ix_users_external_subject", "users", ["external_subject"])
    op.create_index("ix_users_role", "users", ["role"])

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=128), nullable=False),
        sa.Column("refresh_token_family_id", sa.String(length=36), nullable=False),
        sa.Column("user_agent_hash", sa.String(length=64), nullable=True),
        sa.Column("ip_address_hash", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoke_reason", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("refresh_token_hash", name="uq_auth_sessions_refresh_token_hash"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_status", "auth_sessions", ["status"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_index("ix_auth_sessions_family", "auth_sessions", ["refresh_token_family_id"])

    op.create_table(
        "auth_audit_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=255), nullable=True),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("ip_address_hash", sa.String(length=64), nullable=True),
        sa.Column("user_agent_hash", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["auth_sessions.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_auth_audit_logs_user_id", "auth_audit_logs", ["user_id"])
    op.create_index("ix_auth_audit_logs_session_id", "auth_audit_logs", ["session_id"])
    op.create_index("ix_auth_audit_logs_event_type", "auth_audit_logs", ["event_type"])
    op.create_index("ix_auth_audit_logs_created_at", "auth_audit_logs", ["created_at"])

    connection = op.get_bind()
    users = table(
        "users",
        column("id", sa.String),
        column("display_name", sa.String),
        column("auth_provider", sa.String),
        column("external_subject", sa.String),
        column("role", sa.String),
        column("is_active", sa.Boolean),
        column("is_verified", sa.Boolean),
    )
    for identity in sorted(_collect_legacy_identities(connection)):
        op.execute(
            users.insert().values(
                id=identity,
                display_name=identity,
                auth_provider="local",
                external_subject=identity,
                role="teacher",
                is_active=True,
                is_verified=True,
            )
        )


def downgrade() -> None:
    op.drop_index("ix_auth_audit_logs_created_at", table_name="auth_audit_logs")
    op.drop_index("ix_auth_audit_logs_event_type", table_name="auth_audit_logs")
    op.drop_index("ix_auth_audit_logs_session_id", table_name="auth_audit_logs")
    op.drop_index("ix_auth_audit_logs_user_id", table_name="auth_audit_logs")
    op.drop_table("auth_audit_logs")
    op.drop_index("ix_auth_sessions_family", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_status", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_external_subject", table_name="users")
    op.drop_index("ix_users_auth_provider", table_name="users")
    op.drop_index("ix_users_normalized_email", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
