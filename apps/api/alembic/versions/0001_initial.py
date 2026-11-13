"""initial trace schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-10
"""

from alembic import op

from app.db.base import Base
from app.models.domain import *  # noqa: F401,F403

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


# Frozen to the tables that existed at this revision. Later tables are created by their own
# migrations; without this list a fresh database would get them here and break later revisions.
V1_TABLES = {
    "organizations", "users", "matters", "matter_members", "documents", "document_pages",
    "document_chunks", "entities", "entity_mentions", "ai_runs", "events", "event_citations",
    "citations", "memos", "audit_logs", "ingest_jobs", "export_jobs", "saved_searches",
}


def _v1_tables():
    return [table for name, table in Base.metadata.tables.items() if name in V1_TABLES]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=_v1_tables())


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=_v1_tables())
