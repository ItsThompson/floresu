"""baseline: enable pgvector

Establishes the migration chain root and enables the ``vector`` extension so the
semantic-search vector column and ANN index can be created. The dev/prod Postgres
image (``pgvector/pgvector:pg17``) bundles the extension. This baseline is DB
plumbing only; it creates no domain table.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-20

"""

from __future__ import annotations

from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
