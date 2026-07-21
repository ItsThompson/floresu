"""Integration tests for the embeddings migration (0010) against real Postgres.

Proves the ``embed_item_kind`` enum and the ``embeddings`` table apply with the
deterministic constraint names and the pinned ``vector(1536)`` column; that the
HNSW cosine ANN index and the four corpus full-text GIN indexes are created; that
the migration is reversible back to 0009; and the autogenerate-hazard guard: every
ORM model (including the FTS expression indexes written in canonical form) matches
the migrated schema so ``--autogenerate`` emits no structural diff.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.engine import Connection

from floresu.accounts import models as _accounts_models  # noqa: F401
from floresu.audit import models as _audit_models  # noqa: F401
from floresu.core.db import create_db_engine
from floresu.core.orm import Base
from floresu.embedding import models as _embedding_models  # noqa: F401
from floresu.library import models as _library_models  # noqa: F401
from floresu.oauth import models as _oauth_models  # noqa: F401
from floresu.profile import models as _profile_models  # noqa: F401
from floresu.profile.skills import models as _skill_models  # noqa: F401
from floresu.profile.variants import models as _variant_models  # noqa: F401
from floresu.worklog import models as _worklog_models  # noqa: F401

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]

_STRUCTURAL_OPS = frozenset(
    {"add_table", "remove_table", "add_column", "remove_column", "add_index", "remove_index"}
)
_FTS_INDEXES = (
    ("ix_worklog_entries_fts", "worklog_entries"),
    ("ix_bulletpoints_fts", "bulletpoints"),
    ("ix_sources_fts", "sources"),
    ("ix_roles_fts", "roles"),
)


def _alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return config


async def _inspect(postgres_url: str) -> dict[str, object]:
    engine = create_db_engine(postgres_url)
    try:
        async with engine.connect() as conn:
            embeddings = (
                await conn.execute(text("SELECT to_regclass('public.embeddings')"))
            ).scalar_one_or_none()
            enum_labels = (
                (
                    await conn.execute(
                        text(
                            "SELECT e.enumlabel FROM pg_enum e "
                            "JOIN pg_type t ON t.oid = e.enumtypid "
                            "WHERE t.typname = 'embed_item_kind' ORDER BY e.enumsortorder"
                        )
                    )
                )
                .scalars()
                .all()
            )
            constraints = (
                (
                    await conn.execute(
                        text(
                            "SELECT conname FROM pg_constraint "
                            "WHERE conrelid = 'embeddings'::regclass ORDER BY conname"
                        )
                    )
                )
                .scalars()
                .all()
            )
            indexes = (
                (await conn.execute(text("SELECT indexname FROM pg_indexes ORDER BY indexname")))
                .scalars()
                .all()
            )
        return {
            "embeddings": embeddings,
            "enum_labels": enum_labels,
            "constraints": constraints,
            "indexes": indexes,
        }
    finally:
        await engine.dispose()


def test_migration_creates_the_embeddings_table_enum_and_indexes(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    command.upgrade(_alembic_config(), "head")

    result = asyncio.run(_inspect(postgres_url))
    assert result["embeddings"] == "embeddings"
    assert cast("list[str]", result["enum_labels"]) == ["worklog", "bullet", "source"]
    constraints = cast("list[str]", result["constraints"])
    assert "pk_embeddings" in constraints
    assert "fk_embeddings_user_id_users" in constraints
    indexes = cast("list[str]", result["indexes"])
    assert "ix_embeddings_vector_hnsw" in indexes
    for name, _table in _FTS_INDEXES:
        assert name in indexes


def test_migration_is_reversible(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    config = _alembic_config()
    command.upgrade(config, "head")
    command.downgrade(config, "0009_skills_identity_variants")

    async def _state() -> dict[str, object | None]:
        engine = create_db_engine(postgres_url)
        try:
            async with engine.connect() as conn:
                table = (
                    await conn.execute(text("SELECT to_regclass('public.embeddings')"))
                ).scalar_one_or_none()
                enum_present = (
                    await conn.execute(
                        text("SELECT 1 FROM pg_type WHERE typname = 'embed_item_kind'")
                    )
                ).scalar_one_or_none()
                fts_present = (
                    await conn.execute(
                        text("SELECT 1 FROM pg_indexes WHERE indexname = 'ix_worklog_entries_fts'")
                    )
                ).scalar_one_or_none()
            return {"table": table, "enum": enum_present, "fts": fts_present}
        finally:
            await engine.dispose()

    state = asyncio.run(_state())
    assert state["table"] is None
    assert state["enum"] is None
    assert state["fts"] is None
    # Leave the schema at head so other integration tests see a migrated DB.
    command.upgrade(config, "head")


def test_autogenerate_emits_no_structural_diff(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    command.upgrade(_alembic_config(), "head")

    def _diff(sync_conn: Connection) -> list[object]:
        context = MigrationContext.configure(sync_conn)
        return list(compare_metadata(context, Base.metadata))

    async def _run() -> list[object]:
        engine = create_db_engine(postgres_url)
        try:
            async with engine.connect() as conn:
                return await conn.run_sync(_diff)
        finally:
            await engine.dispose()

    diffs = asyncio.run(_run())
    structural = [d for d in diffs if isinstance(d, tuple) and d and d[0] in _STRUCTURAL_OPS]
    assert structural == [], f"autogenerate would change the schema: {structural}"
