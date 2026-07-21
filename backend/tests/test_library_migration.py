"""Integration tests for the library migration (0008) against real Postgres.

Proves the ``bulletpoints`` table and the ``bullet_source`` / ``bullet_worklog``
edge tables apply cleanly with the deterministic constraint names; that the
migration is reversible (all three tables dropped back to 0007); and the
autogenerate-hazard guard: that every ORM model matches the migrated schema so
``alembic revision --autogenerate`` on a head database emits no structural diff.

These tests are synchronous because Alembic's ``env.py`` drives its own
``asyncio.run``; the async inspection runs via ``asyncio.run`` after each command.
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

# Importing every domain's models attaches all tables to Base.metadata, which is
# what env.py does at migration time and what autogenerate diffs against.
from floresu.accounts import models as _accounts_models  # noqa: F401
from floresu.audit import models as _audit_models  # noqa: F401
from floresu.core.db import create_db_engine
from floresu.core.orm import Base
from floresu.library import models as _library_models  # noqa: F401
from floresu.oauth import models as _oauth_models  # noqa: F401
from floresu.profile import models as _profile_models  # noqa: F401
from floresu.worklog import models as _worklog_models  # noqa: F401

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]

_STRUCTURAL_OPS = frozenset(
    {"add_table", "remove_table", "add_column", "remove_column", "add_index", "remove_index"}
)
_LIBRARY_TABLES = ("bulletpoints", "bullet_source", "bullet_worklog")


def _alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return config


async def _inspect(postgres_url: str) -> dict[str, object]:
    engine = create_db_engine(postgres_url)
    try:
        async with engine.connect() as conn:
            tables = {
                table: (
                    await conn.execute(text(f"SELECT to_regclass('public.{table}')"))
                ).scalar_one_or_none()
                for table in _LIBRARY_TABLES
            }
            bullet_constraints = (
                (
                    await conn.execute(
                        text(
                            "SELECT conname FROM pg_constraint "
                            "WHERE conrelid = 'bulletpoints'::regclass ORDER BY conname"
                        )
                    )
                )
                .scalars()
                .all()
            )
            edge_constraints = (
                (
                    await conn.execute(
                        text(
                            "SELECT conname FROM pg_constraint "
                            "WHERE conrelid = 'bullet_source'::regclass "
                            "OR conrelid = 'bullet_worklog'::regclass ORDER BY conname"
                        )
                    )
                )
                .scalars()
                .all()
            )
        return {
            "tables": tables,
            "bullet_constraints": bullet_constraints,
            "edge_constraints": edge_constraints,
        }
    finally:
        await engine.dispose()


def test_migration_creates_the_library_tables_and_names(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    command.upgrade(_alembic_config(), "head")

    result = asyncio.run(_inspect(postgres_url))
    tables = cast("dict[str, object]", result["tables"])
    for table in _LIBRARY_TABLES:
        assert tables[table] == table
    bullet_constraints = cast("list[str]", result["bullet_constraints"])
    assert "pk_bulletpoints" in bullet_constraints
    assert "fk_bulletpoints_user_id_users" in bullet_constraints
    edge_constraints = cast("list[str]", result["edge_constraints"])
    assert "pk_bullet_source" in edge_constraints
    assert "fk_bullet_source_source_id_sources" in edge_constraints
    assert "pk_bullet_worklog" in edge_constraints
    assert "fk_bullet_worklog_worklog_id_worklog_entries" in edge_constraints


def test_migration_is_reversible(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    config = _alembic_config()
    command.upgrade(config, "head")
    command.downgrade(config, "0007_worklog")

    async def _state() -> dict[str, object | None]:
        engine = create_db_engine(postgres_url)
        try:
            async with engine.connect() as conn:
                return {
                    table: (
                        await conn.execute(text(f"SELECT to_regclass('public.{table}')"))
                    ).scalar_one_or_none()
                    for table in _LIBRARY_TABLES
                }
        finally:
            await engine.dispose()

    present = asyncio.run(_state())
    assert all(value is None for value in present.values())
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
