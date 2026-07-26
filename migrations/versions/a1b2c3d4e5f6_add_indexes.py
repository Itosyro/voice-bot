"""Add indexes for hot query paths.

Исходная схема не имела ни одного индекса: get_user_history, /stats,
list_users_with_activity и TTL-cleanup делали full scan — на free-tier
Postgres это заметно грузит БД.

Revision ID: a1b2c3d4e5f6
Revises: f586b9024c60
Create Date: 2026-07-26
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "f586b9024c60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_request_history_user_id",
        "request_history",
        ["user_id"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_request_history_created_at",
        "request_history",
        ["created_at"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_transcription_cache_created_at",
        "transcription_cache",
        ["created_at"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_skills_index_skill_name",
        "skills_index",
        ["skill_name"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_skills_index_skill_name", table_name="skills_index", if_exists=True)
    op.drop_index(
        "ix_transcription_cache_created_at", table_name="transcription_cache", if_exists=True
    )
    op.drop_index("ix_request_history_created_at", table_name="request_history", if_exists=True)
    op.drop_index("ix_request_history_user_id", table_name="request_history", if_exists=True)
