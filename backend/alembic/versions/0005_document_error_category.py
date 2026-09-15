"""document error category

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-15

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    error_category = sa.Enum("user_error", "system_error", name="document_error_category")
    error_category.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "documents",
        sa.Column("error_category", error_category, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "error_category")
    sa.Enum(name="document_error_category").drop(op.get_bind(), checkfirst=True)
