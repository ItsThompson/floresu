"""Integration tests for the corpus resolver against real Postgres.

Proves the resolver composes each kind's embeddable text from the right columns
(worklog title+description, bullet text, source label+summary+role fields), reads
the current content hash, reflects the archive state, and returns ``None`` for a
missing item. Reads are scoped to the owning user.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config

from floresu.accounts.models import User
from floresu.core.db import create_db_engine, create_sessionmaker, transaction
from floresu.embedding.config import EmbedItemKind
from floresu.embedding.corpus import CorpusResolver
from floresu.library.models import Bulletpoint
from floresu.profile.models import Role, Source, SourceKind
from floresu.worklog.models import WorklogEntry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def sessionmaker(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> async_sessionmaker[AsyncSession]:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")
    return create_sessionmaker(create_db_engine(postgres_url))


async def _insert_user(sessionmaker: async_sessionmaker[AsyncSession], email: str) -> int:
    async with sessionmaker() as session, transaction(session):
        user = User(email=email, password_hash="x")
        session.add(user)
        await session.flush()
        return user.id


async def test_resolve_worklog_composes_title_and_description(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _insert_user(sessionmaker, "corpus-wl@test.dev")
    async with sessionmaker() as session, transaction(session):
        entry = WorklogEntry(
            user_id=user_id,
            title="Sharded the write path",
            entry_date=date(2026, 7, 20),
            description="Cut p99 by 40%.",
            content_hash="wl-hash",
        )
        session.add(entry)
        await session.flush()
        entry_id = entry.id

    async with sessionmaker() as session:
        item = await CorpusResolver().resolve(session, user_id, EmbedItemKind.WORKLOG, entry_id)
    assert item is not None
    assert item.text == "Sharded the write path\n\nCut p99 by 40%."
    assert item.content_hash == "wl-hash"
    assert item.archived is False


async def test_resolve_worklog_reflects_archive_state(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _insert_user(sessionmaker, "corpus-wl-arch@test.dev")
    async with sessionmaker() as session, transaction(session):
        entry = WorklogEntry(
            user_id=user_id,
            title="Old note",
            entry_date=date(2026, 1, 1),
            description=None,
            content_hash="h",
            archived_at=datetime.now(UTC),
        )
        session.add(entry)
        await session.flush()
        entry_id = entry.id

    async with sessionmaker() as session:
        item = await CorpusResolver().resolve(session, user_id, EmbedItemKind.WORKLOG, entry_id)
    assert item is not None
    assert item.archived is True
    # A null description leaves no trailing separator.
    assert item.text == "Old note"


async def test_resolve_bullet_uses_the_bullet_text(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _insert_user(sessionmaker, "corpus-bullet@test.dev")
    async with sessionmaker() as session, transaction(session):
        bullet = Bulletpoint(user_id=user_id, text="Led the migration.", content_hash="b-hash")
        session.add(bullet)
        await session.flush()
        bullet_id = bullet.id

    async with sessionmaker() as session:
        item = await CorpusResolver().resolve(session, user_id, EmbedItemKind.BULLET, bullet_id)
    assert item is not None
    assert item.text == "Led the migration."
    assert item.content_hash == "b-hash"


async def test_resolve_source_composes_label_summary_and_role_fields(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _insert_user(sessionmaker, "corpus-source@test.dev")
    async with sessionmaker() as session, transaction(session):
        source = Source(
            user_id=user_id,
            kind=SourceKind.ROLE,
            display_label="Staff Engineer at Acme",
            summary="Owned the platform.",
        )
        session.add(source)
        await session.flush()
        source.id  # noqa: B018 - ensure the id is populated before the role FK
        session.add(
            Role(
                source_id=source.id,
                kind=SourceKind.ROLE,
                company="Acme",
                job_title="Staff Engineer",
            )
        )
        await session.flush()
        source_id = source.id

    async with sessionmaker() as session:
        item = await CorpusResolver().resolve(session, user_id, EmbedItemKind.SOURCE, source_id)
    assert item is not None
    assert item.text == "Staff Engineer at Acme\n\nOwned the platform.\n\nAcme Staff Engineer"
    # Sources carry no stored hash, so the resolver derives a stable one.
    assert item.content_hash != ""
    assert item.archived is False


async def test_resolve_missing_item_is_none(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _insert_user(sessionmaker, "corpus-missing@test.dev")
    async with sessionmaker() as session:
        assert (
            await CorpusResolver().resolve(session, user_id, EmbedItemKind.WORKLOG, 999999) is None
        )


async def test_resolve_is_scoped_to_the_owning_user(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    owner = await _insert_user(sessionmaker, "corpus-owner@test.dev")
    other = await _insert_user(sessionmaker, "corpus-other@test.dev")
    async with sessionmaker() as session, transaction(session):
        bullet = Bulletpoint(user_id=owner, text="Owner's bullet.", content_hash="h")
        session.add(bullet)
        await session.flush()
        bullet_id = bullet.id

    async with sessionmaker() as session:
        resolver = CorpusResolver()
        assert await resolver.resolve(session, other, EmbedItemKind.BULLET, bullet_id) is None
        assert await resolver.resolve(session, owner, EmbedItemKind.BULLET, bullet_id) is not None
