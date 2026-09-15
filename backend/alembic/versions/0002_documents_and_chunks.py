"""documents and chunks

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-12

"""
from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Matches LocalEmbeddingProvider's bge-small-en-v1.5 output (app/config.py's
# EMBEDDING_PROVIDER default) — the pgvector column is fixed-width, so this is a
# real schema commitment, not just a default value. See docs/embeddings.md for
# what switching to the 1536-dim OpenAI provider actually requires (a new
# migration to resize this column plus re-indexing existing chunks, not just an
# env var flip).
EMBEDDING_DIMENSIONS = 384


def upgrade() -> None:
    document_status = sa.Enum("queued", "processing", "ready", "failed", name="document_status")
    document_format = sa.Enum("pdf", "txt", "md", name="document_format")

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("format", document_format, nullable=False),
        sa.Column("status", document_status, nullable=False, server_default="queued"),
        sa.Column("error_reason", sa.Text(), nullable=True),
        sa.Column("object_storage_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_documents_session_id", "documents", ["session_id"])

    op.create_table(
        "chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("location_ref", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(EMBEDDING_DIMENSIONS), nullable=False),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("embedding_version", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])


def downgrade() -> None:
    op.drop_table("chunks")
    op.drop_table("documents")
    sa.Enum(name="document_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="document_format").drop(op.get_bind(), checkfirst=True)
