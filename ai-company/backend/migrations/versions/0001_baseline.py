"""Nền tảng CSDL: extension pgvector/pg_trgm/unaccent, schema cho LangGraph, bảng thông tin hệ thống.

Revision ID: 0001_baseline
Revises:
"""

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    # Checkpoint của LangGraph nằm trong schema riêng (ARCHITECTURE ADR-05, DATABASE_SCHEMA §6)
    op.execute("CREATE SCHEMA IF NOT EXISTS langgraph")
    op.execute(
        """
        CREATE TABLE system_meta (
          key text PRIMARY KEY,
          value text NOT NULL,
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("INSERT INTO system_meta(key, value) VALUES ('installed_at', now()::text)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS system_meta")
    op.execute("DROP SCHEMA IF EXISTS langgraph CASCADE")
    # Giữ extension: có thể đang được dùng ở nơi khác trong CSDL; gỡ extension cần quyền superuser.
