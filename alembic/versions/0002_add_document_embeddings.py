"""Add pgvector embeddings while preserving legacy documents.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("documents", sa.Column("embedding", VECTOR(384), nullable=True))
    # NOT VALID preserves old NULL rows but rejects new/updated rows without vectors.
    op.create_check_constraint(
        "documents_embedding_required",
        "documents",
        "embedding IS NOT NULL",
        postgresql_not_valid=True,
    )


def downgrade() -> None:
    op.drop_constraint("documents_embedding_required", "documents", type_="check")
    op.drop_column("documents", "embedding")
    # The extension may also be used by other tables; do not drop it.
