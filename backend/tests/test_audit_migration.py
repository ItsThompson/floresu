"""Integration tests for the audit_log migration (0004) against real Postgres.

Proves the table, the native ``actor_type`` enum, and the feed index apply cleanly
with the deterministic constraint names, that the migration is reversible (table
and enum both dropped), and: the autogenerate-hazard guard: that every ORM model
matches the migrated schema so ``alembic revision --autogenerate`` on a head
database emits no structural diff.

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
# what env.py does at migration time and what autogenerate diffs against. Without
# the full set, autogenerate would spuriously want to drop the absent tables.
from floresu.accounts import models as _accounts_models  # noqa: F401
from floresu.audit import models as _audit_models  # noqa: F401
from floresu.core.db import create_db_engine
from floresu.core.orm import Base

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]

_STRUCTURAL_OPS = frozenset(
    {"add_table", "remove_table", "add_column", "remove_column", "add_index", "remove_index"}
)


def _alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return config


async def _inspect(postgres_url: str) -> dict[str, object]:
    engine = create_db_engine(postgres_url)
    try:
        async with engine.connect() as conn:
            table = (
                await conn.execute(text("SELECT to_regclass('public.audit_log')"))
            ).scalar_one_or_none()
            enum = (
                await conn.execute(text("SELECT 1 FROM pg_type WHERE typname = 'actor_type'"))
            ).scalar_one_or_none()
            constraints = (
                (
                    await conn.execute(
                        text(
                            "SELECT conname FROM pg_constraint "
                            "WHERE conrelid = 'audit_log'::regclass ORDER BY conname"
                        )
                    )
                )
                .scalars()
                .all()
            )
            indexes = (
                (
                    await conn.execute(
                        text(
                            "SELECT indexname FROM pg_indexes "
                            "WHERE tablename = 'audit_log' ORDER BY indexname"
                        )
                    )
                )
                .scalars()
                .all()
            )
        return {"table": table, "enum": enum, "constraints": constraints, "indexes": indexes}
    finally:
        await engine.dispose()


def test_audit_migration_creates_the_table_enum_and_index(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    command.upgrade(_alembic_config(), "head")

    result = asyncio.run(_inspect(postgres_url))
    assert result["table"] == "audit_log"
    assert result["enum"] == 1
    # Deterministic naming convention (pk_/fk_/ix_).
    assert "pk_audit_log" in cast("list[str]", result["constraints"])
    assert "fk_audit_log_user_id_users" in cast("list[str]", result["constraints"])
    assert "ix_audit_log_user_id_id" in cast("list[str]", result["indexes"])


def test_audit_migration_is_reversible(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    config = _alembic_config()
    command.upgrade(config, "head")
    command.downgrade(config, "0003_accounts_sessions")

    async def _state() -> tuple[object, object]:
        engine = create_db_engine(postgres_url)
        try:
            async with engine.connect() as conn:
                table = (
                    await conn.execute(text("SELECT to_regclass('public.audit_log')"))
                ).scalar_one_or_none()
                enum = (
                    await conn.execute(text("SELECT 1 FROM pg_type WHERE typname = 'actor_type'"))
                ).scalar_one_or_none()
            return table, enum
        finally:
            await engine.dispose()

    table, enum = asyncio.run(_state())
    # Both the table and the enum type it owns are dropped on downgrade.
    assert table is None
    assert enum is None
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
