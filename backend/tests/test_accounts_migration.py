"""Integration tests for the accounts migration (0003) against real Postgres.

Proves the onboarding flag and the revoked-session blacklist apply cleanly, the
migration is reversible, and: the autogenerate-hazard fix: that the ``User`` /
``RevokedSession`` ORM models exactly match the migrated schema, so
``alembic revision --autogenerate`` on a head database emits no structural diff
(no spurious DROP/CREATE of ``users`` or ``revoked_sessions``).
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

# Importing the models attaches the accounts tables to Base.metadata, which is
# what env.py does at migration time and what autogenerate diffs against.
from floresu.accounts import models as _accounts_models  # noqa: F401
from floresu.core.db import create_db_engine
from floresu.core.orm import Base

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]

# The structural diff kinds that would signal the model and schema disagree; the
# T2 hazard is precisely a spurious remove_table on ``users``.
_STRUCTURAL_OPS = frozenset(
    {"add_table", "remove_table", "add_column", "remove_column", "add_index", "remove_index"}
)


def _alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return config


def test_accounts_migration_adds_the_flag_and_blacklist_table(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    command.upgrade(_alembic_config(), "head")

    async def _inspect() -> dict[str, object]:
        engine = create_db_engine(postgres_url)
        try:
            async with engine.connect() as conn:
                flag_default = (
                    await conn.execute(
                        text(
                            "SELECT column_default FROM information_schema.columns "
                            "WHERE table_name = 'users' "
                            "AND column_name = 'has_completed_onboarding'"
                        )
                    )
                ).scalar_one_or_none()
                blacklist = (
                    await conn.execute(text("SELECT to_regclass('public.revoked_sessions')"))
                ).scalar_one_or_none()
                constraints = (
                    (
                        await conn.execute(
                            text(
                                "SELECT conname FROM pg_constraint "
                                "WHERE conrelid = 'revoked_sessions'::regclass ORDER BY conname"
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
                                "WHERE tablename = 'revoked_sessions' ORDER BY indexname"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
            return {
                "flag_default": flag_default,
                "blacklist": blacklist,
                "constraints": constraints,
                "indexes": indexes,
            }
        finally:
            await engine.dispose()

    result = asyncio.run(_inspect())
    assert result["flag_default"] is not None and "false" in str(result["flag_default"])
    assert result["blacklist"] == "revoked_sessions"
    # Deterministic naming convention (pk_/ix_).
    assert "pk_revoked_sessions" in cast("list[str]", result["constraints"])
    assert "ix_revoked_sessions_user_id" in cast("list[str]", result["indexes"])


def test_accounts_migration_is_reversible(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    config = _alembic_config()
    command.upgrade(config, "head")
    command.downgrade(config, "0002_users")

    async def _state() -> tuple[object, bool]:
        engine = create_db_engine(postgres_url)
        try:
            async with engine.connect() as conn:
                blacklist = (
                    await conn.execute(text("SELECT to_regclass('public.revoked_sessions')"))
                ).scalar_one_or_none()
                has_flag = (
                    await conn.execute(
                        text(
                            "SELECT 1 FROM information_schema.columns "
                            "WHERE table_name = 'users' "
                            "AND column_name = 'has_completed_onboarding'"
                        )
                    )
                ).scalar_one_or_none()
            return blacklist, has_flag is not None
        finally:
            await engine.dispose()

    blacklist, has_flag = asyncio.run(_state())
    assert blacklist is None
    assert has_flag is False
    # Leave the schema at head so other integration tests see a migrated DB.
    command.upgrade(config, "head")


def test_autogenerate_emits_no_structural_diff(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The T2 handoff hazard: without the ORM models, autogenerate would DROP the
    # accounts tables. With them imported onto Base.metadata, a head database
    # produces no add/remove of any table, column, or index.
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
