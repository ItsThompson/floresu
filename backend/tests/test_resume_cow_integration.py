"""End-to-end copy-on-write and promote tests against real Postgres.

Runs the real :class:`ResumeService`, the real :class:`LibraryCanonicalBulletWriter`
over the SQLAlchemy library repository, the real bullet-text resolver, and the
composed write-event publisher (audit as its transactional consumer), so each path
proves its full effect against real SQL in a single transaction: the canonical
``bulletpoints`` row, the resume ``document``, the write-derived
``resume_bullet_ref`` index, the appended ``resume_revisions`` snapshot, and the
``audit_log`` rows (including the promote's bullet-create and resume-promote rows).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from floresu.accounts.models import User
from floresu.audit.models import AuditLog
from floresu.audit.wiring import build_write_event_publisher
from floresu.core.actor import Actor, ActorType
from floresu.core.db import create_db_engine, create_sessionmaker, transaction
from floresu.core.events import REEMBED_CONTENT_HASH_KEY, SCOPE_METADATA_KEY
from floresu.library.cow import LibraryCanonicalBulletWriter
from floresu.library.models import Bulletpoint, BulletSource, BulletWorklog
from floresu.library.repository import SqlAlchemyLibraryRepository
from floresu.library.schemas import BulletpointWrite
from floresu.library.service import LibraryService
from floresu.profile.models import Source, SourceKind
from floresu.resumes.cow import EditChannel, ResumeEditScope
from floresu.resumes.models import Resume, ResumeBulletRef, ResumeRevision
from floresu.resumes.repository import SqlAlchemyResumeRepository
from floresu.resumes.resolver import SqlAlchemyBulletTextResolver
from floresu.resumes.schemas import ScopeEditRequest
from floresu.resumes.service import ResumeService
from floresu.worklog.models import WorklogEntry
from tests.resumes_fakes import build_create_request, build_update

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]
_HUMAN = Actor(type=ActorType.HUMAN)


@pytest.fixture
def migrated_url(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")
    return postgres_url


def _resumes(session: AsyncSession) -> ResumeService:
    publisher = build_write_event_publisher()
    return ResumeService(
        session,
        SqlAlchemyResumeRepository(session),
        SqlAlchemyBulletTextResolver(session),
        publisher,
        LibraryCanonicalBulletWriter(session, SqlAlchemyLibraryRepository(session), publisher),
    )


async def _insert_user(sessionmaker: async_sessionmaker[AsyncSession], email: str) -> int:
    async with sessionmaker() as session, transaction(session):
        user = User(email=email, password_hash="x")
        session.add(user)
        await session.flush()
        return user.id


async def _create_bullet(
    sessionmaker: async_sessionmaker[AsyncSession], user_id: int, text: str
) -> int:
    async with sessionmaker() as session:
        service = LibraryService(
            session, SqlAlchemyLibraryRepository(session), build_write_event_publisher()
        )
        record = await service.create(str(user_id), _HUMAN, BulletpointWrite(text=text))
        return record.id


async def _insert_source(sessionmaker: async_sessionmaker[AsyncSession], user_id: int) -> int:
    async with sessionmaker() as session, transaction(session):
        source = Source(user_id=user_id, kind=SourceKind.ROLE, display_label="Acme")
        session.add(source)
        await session.flush()
        return source.id


async def _insert_worklog(sessionmaker: async_sessionmaker[AsyncSession], user_id: int) -> int:
    async with sessionmaker() as session, transaction(session):
        entry = WorklogEntry(
            user_id=user_id, title="Shipped it", entry_date=date(2026, 1, 1), content_hash="h"
        )
        session.add(entry)
        await session.flush()
        return entry.id


def _ref_section(bullet_id: int, item_id: str = "a") -> dict[str, object]:
    return {
        "id": "sec-work",
        "kind": "work",
        "title": "Experience",
        "item_order": [item_id],
        "items": {item_id: {"id": item_id, "kind": "library_ref", "bullet_id": bullet_id}},
    }


def _local_section(
    text: str, item_id: str = "a", source_refs: dict[str, object] | None = None
) -> dict[str, object]:
    item: dict[str, object] = {"id": item_id, "kind": "local", "text": text}
    if source_refs is not None:
        item["source_refs"] = source_refs
    return {
        "id": "sec-work",
        "kind": "work",
        "title": "Experience",
        "item_order": [item_id],
        "items": {item_id: item},
    }


async def _referencing_resume(
    sessionmaker: async_sessionmaker[AsyncSession], user_id: int, bullet_id: int
) -> int:
    async with sessionmaker() as session:
        record = await _resumes(session).create(str(user_id), _HUMAN, build_create_request())
        resume_id = record.id
    async with sessionmaker() as session:
        await _resumes(session).update(
            str(user_id), resume_id, _HUMAN, 1, build_update(sections=[_ref_section(bullet_id)])
        )
    return resume_id


async def test_everywhere_edits_the_canonical_bullet_and_re_embeds(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "cow-everywhere@example.com")
        bullet_id = await _create_bullet(sessionmaker, user_id, "Cut latency 40%.")
        resume_id = await _referencing_resume(sessionmaker, user_id, bullet_id)

        async with sessionmaker() as session:
            result = await _resumes(session).bullet_update(
                str(user_id),
                _HUMAN,
                EditChannel.WEB,
                ScopeEditRequest(
                    bullet_id=bullet_id,
                    new_text="Cut latency 80%.",
                    scope=ResumeEditScope.EVERYWHERE,
                    if_match_bullet_revision=1,
                ),
            )
        assert result.outcome == "edited_everywhere"

        async with sessionmaker() as session:
            bullet = (
                await session.execute(select(Bulletpoint).where(Bulletpoint.id == bullet_id))
            ).scalar_one()
            assert bullet.text == "Cut latency 80%."
            assert bullet.revision == 2
            # The reference still stands; the resume resolves the new text on read.
            refs = (
                (
                    await session.execute(
                        select(ResumeBulletRef.bullet_id).where(
                            ResumeBulletRef.resume_id == resume_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert list(refs) == [bullet_id]
            edit_audit = (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.user_id == user_id,
                        AuditLog.entity_type == "bullet",
                        AuditLog.entity_id == bullet_id,
                        AuditLog.action == "update",
                    )
                )
            ).scalar_one()
            assert (edit_audit.event_metadata or {})[SCOPE_METADATA_KEY] == "everywhere"
            assert (edit_audit.event_metadata or {})[REEMBED_CONTENT_HASH_KEY]
    finally:
        await engine.dispose()


async def test_this_resume_forks_locally_and_leaves_the_canonical(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "cow-fork@example.com")
        bullet_id = await _create_bullet(sessionmaker, user_id, "Shared framing.")
        resume_a = await _referencing_resume(sessionmaker, user_id, bullet_id)
        resume_b = await _referencing_resume(sessionmaker, user_id, bullet_id)

        async with sessionmaker() as session:
            resume = (
                await session.execute(select(Resume).where(Resume.id == resume_a))
            ).scalar_one()
            revision = resume.revision
        async with sessionmaker() as session:
            result = await _resumes(session).bullet_update(
                str(user_id),
                _HUMAN,
                EditChannel.WEB,
                ScopeEditRequest(
                    bullet_id=bullet_id,
                    new_text="Forked framing.",
                    scope=ResumeEditScope.THIS_RESUME,
                    resume_id=resume_a,
                    if_match_resume_revision=revision,
                ),
            )
        assert result.outcome == "forked_this_resume"

        async with sessionmaker() as session:
            bullet = (
                await session.execute(select(Bulletpoint).where(Bulletpoint.id == bullet_id))
            ).scalar_one()
            assert bullet.text == "Shared framing."  # canonical untouched
            item = (
                (await session.execute(select(Resume).where(Resume.id == resume_a)))
                .scalar_one()
                .document["sections"][0]["items"]["a"]
            )
            assert item["kind"] == "local"
            assert item["forked_from_bullet_id"] == bullet_id
            # The index drops this resume's row; the other resume still references it.
            a_refs = (
                (
                    await session.execute(
                        select(ResumeBulletRef.bullet_id).where(
                            ResumeBulletRef.resume_id == resume_a
                        )
                    )
                )
                .scalars()
                .all()
            )
            b_refs = (
                (
                    await session.execute(
                        select(ResumeBulletRef.bullet_id).where(
                            ResumeBulletRef.resume_id == resume_b
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert list(a_refs) == []
            assert list(b_refs) == [bullet_id]
            fork_audit = (
                (
                    await session.execute(
                        select(AuditLog)
                        .where(
                            AuditLog.user_id == user_id,
                            AuditLog.entity_type == "resume",
                            AuditLog.entity_id == resume_a,
                            AuditLog.action == "update",
                        )
                        .order_by(AuditLog.id)
                    )
                )
                .scalars()
                .all()[-1]
            )
            assert (fork_audit.event_metadata or {})[SCOPE_METADATA_KEY] == "this_resume"
    finally:
        await engine.dispose()


async def test_promote_creates_a_canonical_bullet_with_links_and_reindexes(
    migrated_url: str,
) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "cow-promote@example.com")
        source_id = await _insert_source(sessionmaker, user_id)
        worklog_id = await _insert_worklog(sessionmaker, user_id)

        async with sessionmaker() as session:
            record = await _resumes(session).create(str(user_id), _HUMAN, build_create_request())
            resume_id = record.id
        async with sessionmaker() as session:
            await _resumes(session).update(
                str(user_id),
                resume_id,
                _HUMAN,
                1,
                build_update(
                    sections=[
                        _local_section(
                            "Promoted framing.",
                            source_refs={
                                "source_ids": [source_id],
                                "worklog_ids": [worklog_id],
                            },
                        )
                    ]
                ),
            )

        async with sessionmaker() as session:
            resume = (
                await session.execute(select(Resume).where(Resume.id == resume_id))
            ).scalar_one()
            revision = resume.revision
        async with sessionmaker() as session:
            promoted = await _resumes(session).promote(
                str(user_id), resume_id, _HUMAN, revision, "a"
            )
        item = promoted.document.sections[0].items["a"]
        new_bullet_id = item.bullet_id  # type: ignore[union-attr]

        async with sessionmaker() as session:
            bullet = (
                await session.execute(select(Bulletpoint).where(Bulletpoint.id == new_bullet_id))
            ).scalar_one()
            assert bullet.text == "Promoted framing."
            source_edges = (
                (
                    await session.execute(
                        select(BulletSource.source_id).where(
                            BulletSource.bullet_id == new_bullet_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            worklog_edges = (
                (
                    await session.execute(
                        select(BulletWorklog.worklog_id).where(
                            BulletWorklog.bullet_id == new_bullet_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert list(source_edges) == [source_id]
            assert list(worklog_edges) == [worklog_id]
            # The write-derived index now points at the promoted canonical bullet.
            refs = (
                (
                    await session.execute(
                        select(ResumeBulletRef.bullet_id).where(
                            ResumeBulletRef.resume_id == resume_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert list(refs) == [new_bullet_id]
            # Two audited writes: the bullet create (re-embed trigger) and the promote.
            create_audit = (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.user_id == user_id,
                        AuditLog.entity_type == "bullet",
                        AuditLog.entity_id == new_bullet_id,
                        AuditLog.action == "create",
                    )
                )
            ).scalar_one()
            assert (create_audit.event_metadata or {})[REEMBED_CONTENT_HASH_KEY]
            promote_audit = (
                await session.execute(
                    select(func.count())
                    .select_from(AuditLog)
                    .where(
                        AuditLog.user_id == user_id,
                        AuditLog.entity_type == "resume",
                        AuditLog.entity_id == resume_id,
                        AuditLog.action == "promote",
                    )
                )
            ).scalar_one()
            assert promote_audit == 1
            # The promote appended a resume revision snapshot with the swapped item inline.
            snapshot = (
                await session.execute(
                    select(ResumeRevision.document).where(
                        ResumeRevision.resume_id == resume_id,
                        ResumeRevision.revision_no == revision + 1,
                    )
                )
            ).scalar_one()
            assert snapshot["sections"][0]["items"]["a"]["text"] == "Promoted framing."
    finally:
        await engine.dispose()
