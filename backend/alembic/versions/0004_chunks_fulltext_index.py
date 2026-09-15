"""chunks full-text search index

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-15

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Functional GIN index on the same to_tsvector('english', content) expression
    # ChunkRepository.search_ready's keyword branch queries against (issue #11) — lets
    # Postgres use an index for the @@ match instead of a full scan, without adding a
    # generated column (and the ORM/migration churn that would bring) for what's still
    # a small-corpus assignment project.
    op.execute(
        "CREATE INDEX ix_chunks_content_fts ON chunks "
        "USING gin (to_tsvector('english', content))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_content_fts")
