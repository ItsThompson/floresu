"""Integration tests for the sources migration (0006) against real Postgres.

Proves the supertable and its four kind-locked subtype tables, the native
``source_kind`` enum, and the ordering index apply cleanly with the deterministic
constraint names; that the migration is reversible (all tables and the enum
dropped); and the autogenerate-hazard guard: that every ORM model matches the
migrated schema so ``alembic revision --autogenerate`` on a head database emits no
structural diff.

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
from floresu.oauth import models as _oauth_models  # noqa: F401
from floresu.profile import models as _profile_models  # noqa: F401

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]

_STRUCTURAL_OPS = frozenset(
    {"add_table", "remove_table", "add_column", "remove_column", "add_index", "remove_index"}
)
_SUBTYPE_TABLES = ("roles", "projects", "certifications", "education")


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
                for table in ("sources", *_SUBTYPE_TABLES)
            }
            enum = (
                await conn.execute(text("SELECT 1 FROM pg_type WHERE typname = 'source_kind'"))
            ).scalar_one_or_none()
            source_constraints = (
                (
                    await conn.execute(
                        text(
                            "SELECT conname FROM pg_constraint "
                            "WHERE conrelid = 'sources'::regclass ORDER BY conname"
                        )
                    )
                )
                .scalars()
                .all()
            )
            role_constraints = (
                (
                    await conn.execute(
                        text(
                            "SELECT conname FROM pg_constraint "
                            "WHERE conrelid = 'roles'::regclass ORDER BY conname"
                        )
                    )
                )
                .scalars()
                .all()
            )
        return {
            "tables": tables,
            "enum": enum,
            "source_constraints": source_constraints,
            "role_constraints": role_constraints,
        }
    finally:
        await engine.dispose()


def test_migration_creates_the_supertable_subtypes_enum_and_names(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    command.upgrade(_alembic_config(), "head")

    result = asyncio.run(_inspect(postgres_url))
    tables = cast("dict[str, object]", result["tables"])
    assert tables["sources"] == "sources"
    for table in _SUBTYPE_TABLES:
        assert tables[table] == table
    assert result["enum"] == 1
    # Deterministic naming on the base table (pk_/fk_/uq_) and a subtype (ck_/fk_).
    source_constraints = cast("list[str]", result["source_constraints"])
    assert "pk_sources" in source_constraints
    assert "fk_sources_user_id_users" in source_constraints
    assert "uq_sources_id_kind" in source_constraints
    role_constraints = cast("list[str]", result["role_constraints"])
    assert "ck_roles_kind" in role_constraints
    assert "fk_roles_source_id_sources" in role_constraints


def test_migration_is_reversible(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    config = _alembic_config()
    command.upgrade(config, "head")
    command.downgrade(config, "0005_oauth")

    async def _state() -> tuple[object, object]:
        engine = create_db_engine(postgres_url)
        try:
            async with engine.connect() as conn:
                sources = (
                    await conn.execute(text("SELECT to_regclass('public.sources')"))
                ).scalar_one_or_none()
                enum = (
                    await conn.execute(text("SELECT 1 FROM pg_type WHERE typname = 'source_kind'"))
                ).scalar_one_or_none()
            return sources, enum
        finally:
            await engine.dispose()

    sources, enum = asyncio.run(_state())
    assert sources is None
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
