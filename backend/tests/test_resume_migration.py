"""Integration tests for the resume migration (0010) against real Postgres.

Proves the ``job_applications`` / ``resumes`` / ``resume_bullet_ref`` /
``resume_revisions`` tables apply cleanly with the deterministic constraint names
(including the 1:1 ``UNIQUE`` and the application-only ``CHECK``); that the
migration is reversible back to 0009; and the autogenerate-hazard guard: that every
ORM model matches the migrated schema so ``alembic revision --autogenerate`` on a
head database emits no structural diff.
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
from floresu.profile.skills import models as _skill_models  # noqa: F401
from floresu.profile.variants import models as _variant_models  # noqa: F401
from floresu.resumes import models as _resume_models  # noqa: F401
from floresu.worklog import models as _worklog_models  # noqa: F401

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]

_STRUCTURAL_OPS = frozenset(
    {"add_table", "remove_table", "add_column", "remove_column", "add_index", "remove_index"}
)
_RESUME_TABLES = ("job_applications", "resumes", "resume_bullet_ref", "resume_revisions")


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
                for table in _RESUME_TABLES
            }
            resume_constraints = (
                (
                    await conn.execute(
                        text(
                            "SELECT conname FROM pg_constraint "
                            "WHERE conrelid = 'resumes'::regclass ORDER BY conname"
                        )
                    )
                )
                .scalars()
                .all()
            )
        return {"tables": tables, "resume_constraints": resume_constraints}
    finally:
        await engine.dispose()


def test_migration_creates_the_resume_tables_and_names(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    command.upgrade(_alembic_config(), "head")

    result = asyncio.run(_inspect(postgres_url))
    tables = cast("dict[str, object]", result["tables"])
    for table in _RESUME_TABLES:
        assert tables[table] == table
    constraints = cast("list[str]", result["resume_constraints"])
    assert "pk_resumes" in constraints
    assert "fk_resumes_user_id_users" in constraints
    assert "fk_resumes_job_application_id_job_applications" in constraints
    assert "uq_resumes_job_application_id" in constraints
    assert "ck_resumes_job_application_kind" in constraints


def test_migration_is_reversible(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    config = _alembic_config()
    command.upgrade(config, "head")
    command.downgrade(config, "0009_skills_identity_variants")

    async def _state() -> dict[str, object | None]:
        engine = create_db_engine(postgres_url)
        try:
            async with engine.connect() as conn:
                return {
                    table: (
                        await conn.execute(text(f"SELECT to_regclass('public.{table}')"))
                    ).scalar_one_or_none()
                    for table in _RESUME_TABLES
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
