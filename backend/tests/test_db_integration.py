"""Integration tests: the DB layer and the baseline migration against real Postgres.

Uses testcontainers to run ``pgvector/pgvector:pg17`` (the pinned dev/prod image),
so ``CREATE EXTENSION vector`` in the baseline applies. Skipped automatically when
Docker is unavailable (see the ``postgres_url`` fixture), so a Docker-less checkout
still runs the unit suite; CI has Docker and runs these.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from floresu.core.db import (
    create_db_engine,
    create_sessionmaker,
    db_readiness_check,
    fetch_optional,
    is_unique_violation,
    transaction,
)

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]

_metadata = sa.MetaData()
_widgets = sa.Table(
    "widgets",
    _metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("name", sa.String(50), nullable=False, unique=True),
)


def _alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return config


def test_alembic_upgrade_head_creates_users_and_enables_pgvector(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # env.py reads DATABASE_URL from settings; point it at the container. This
    # test is sync because Alembic's env.py drives its own asyncio.run().
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    command.upgrade(_alembic_config(), "head")

    async def _inspect() -> dict[str, object]:
        engine = create_db_engine(postgres_url)
        try:
            async with engine.connect() as conn:
                version = (
                    await conn.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one_or_none()
                has_vector = (
                    await conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
                ).scalar_one_or_none()
                constraints = (
                    (
                        await conn.execute(
                            text(
                                "SELECT conname FROM pg_constraint "
                                "WHERE conrelid = 'users'::regclass ORDER BY conname"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
            return {"version": version, "has_vector": has_vector, "constraints": constraints}
        finally:
            await engine.dispose()

    result = asyncio.run(_inspect())
    # Migration head after the wave integration: the embeddings slice
    # (0011_embeddings) chained onto the resume Output layer (0010_resumes), which
    # chains onto skills + identity_variants (0009), the library domain (0008), the
    # worklog domain (0007), the sources supertable (0006), audit (0004), and OAuth
    # (0005).
    assert result["version"] == "0011_embeddings"
    assert result["has_vector"] == 1
    # Deterministic constraint-naming convention (ix_/uq_/ck_/fk_/pk_).
    assert result["constraints"] == ["pk_users", "uq_users_email"]


def test_alembic_downgrade_is_reversible(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    config = _alembic_config()
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    async def _users_present() -> bool:
        engine = create_db_engine(postgres_url)
        try:
            async with engine.connect() as conn:
                found = (
                    await conn.execute(text("SELECT to_regclass('public.users')"))
                ).scalar_one_or_none()
            return found is not None
        finally:
            await engine.dispose()

    assert asyncio.run(_users_present()) is False
    # Leave the schema at head so other integration tests see a migrated DB.
    command.upgrade(config, "head")


async def test_transaction_commits_then_rolls_back_against_real_postgres(
    postgres_url: str,
) -> None:
    engine = create_db_engine(postgres_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(_metadata.create_all)

        # Commit path: a clean exit persists the row.
        async with sessionmaker() as session, transaction(session):
            await session.execute(sa.insert(_widgets).values(id=1, name="alpha"))
        async with sessionmaker() as session:
            committed = await fetch_optional(
                session, sa.select(_widgets.c.name).where(_widgets.c.id == 1)
            )

        # Rollback path: a raised error discards the row and re-raises.
        with pytest.raises(ValueError, match="boom"):
            async with sessionmaker() as session, transaction(session):
                await session.execute(sa.insert(_widgets).values(id=2, name="beta"))
                raise ValueError("boom")
        async with sessionmaker() as session:
            rolled_back = await fetch_optional(
                session, sa.select(_widgets.c.name).where(_widgets.c.id == 2)
            )

        async with engine.begin() as conn:
            await conn.run_sync(_metadata.drop_all)
    finally:
        await engine.dispose()

    assert committed == "alpha"
    assert rolled_back is None


async def test_unique_violation_is_detected_on_duplicate_insert(postgres_url: str) -> None:
    engine = create_db_engine(postgres_url)
    sessionmaker = create_sessionmaker(engine)
    caught: IntegrityError | None = None
    try:
        async with engine.begin() as conn:
            await conn.run_sync(_metadata.create_all)

        async with sessionmaker() as session:
            await session.execute(sa.insert(_widgets).values(id=1, name="dup"))
            await session.commit()
            try:
                await session.execute(sa.insert(_widgets).values(id=2, name="dup"))
                await session.commit()
            except IntegrityError as exc:
                caught = exc

        async with engine.begin() as conn:
            await conn.run_sync(_metadata.drop_all)
    finally:
        await engine.dispose()

    assert caught is not None
    assert is_unique_violation(caught) is True


async def test_db_readiness_check_ok_against_real_db(postgres_url: str) -> None:
    engine = create_db_engine(postgres_url)
    try:
        result = await db_readiness_check(engine)()
    finally:
        await engine.dispose()
    assert result.name == "postgres"
    assert result.ok is True
    assert result.detail is None
