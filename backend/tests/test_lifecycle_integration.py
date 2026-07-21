"""End-to-end lifecycle tests against real Postgres: cascade, purge, and account delete.

Builds a real record graph (source + worklog + bullet + resume, with provenance
edges and stored vectors) through direct ORM inserts, then runs the real
:class:`LifecycleService` over the SQLAlchemy repositories and the composed
write-event publisher (audit as its transactional consumer). Proves the
database-enforced cascade the data model promises: a permanent delete removes the
subtype, edge, revision, and ref rows via ``ON DELETE CASCADE`` while leaving
attached siblings, and separately purges the polymorphic ``embeddings`` row that
has no FK to cascade from. Account deletion cascades every ``user_id``-owned table
(``embeddings`` included) and revokes the OAuth grant chain that carries the user
id without a FK.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Select, func, select

from floresu.accounts.models import RevokedSession, User
from floresu.audit.models import AuditLog
from floresu.audit.wiring import build_write_event_publisher
from floresu.core.actor import Actor, ActorType
from floresu.core.db import create_db_engine, create_sessionmaker, transaction
from floresu.embedding.config import EMBEDDING_DIMENSION, EMBEDDING_MODEL, EmbedItemKind
from floresu.embedding.models import Embedding
from floresu.embedding.repository import SqlAlchemyEmbeddingRepository
from floresu.library.models import Bulletpoint, BulletSource, BulletWorklog
from floresu.lifecycle.export_repository import SqlAlchemyExportRepository
from floresu.lifecycle.repository import SqlAlchemyLifecycleRepository
from floresu.lifecycle.service import LifecycleService
from floresu.oauth.models import OAuthGrant, OAuthRefreshToken
from floresu.profile.models import Role, Source, SourceKind
from floresu.resumes.models import (
    Resume,
    ResumeBulletRef,
    ResumeKind,
    ResumeRevision,
    ResumeStatus,
)
from floresu.worklog.models import Tag, WorklogEntry, WorklogSource, WorklogTag

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]
_HUMAN = Actor(type=ActorType.HUMAN)
_VECTOR = [0.1] * EMBEDDING_DIMENSION


@pytest.fixture
def migrated_url(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """Point settings at the container and bring it to head (idempotent per test)."""
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")
    return postgres_url


def _service(session: AsyncSession) -> LifecycleService:
    return LifecycleService(
        session,
        SqlAlchemyLifecycleRepository(session),
        SqlAlchemyExportRepository(session),
        SqlAlchemyEmbeddingRepository(session),
        build_write_event_publisher(),
    )


async def _insert_user(sessionmaker: async_sessionmaker[AsyncSession], email: str) -> int:
    async with sessionmaker() as session, transaction(session):
        user = User(email=email, password_hash="x")
        session.add(user)
        await session.flush()
        return user.id


class _Graph:
    """Ids of the seeded record graph for one user."""

    def __init__(self, source_id: int, worklog_id: int, bullet_id: int, resume_id: int) -> None:
        self.source_id = source_id
        self.worklog_id = worklog_id
        self.bullet_id = bullet_id
        self.resume_id = resume_id


async def _seed_graph(sessionmaker: async_sessionmaker[AsyncSession], user_id: int) -> _Graph:
    """Insert a source+worklog+bullet+resume graph with edges and stored vectors."""
    async with sessionmaker() as session, transaction(session):
        source = Source(
            user_id=user_id, kind=SourceKind.ROLE, display_label="Staff at Acme", sort_order=0
        )
        session.add(source)
        await session.flush()
        session.add(Role(source_id=source.id, kind=SourceKind.ROLE, company="Acme", job_title="SE"))

        entry = WorklogEntry(
            user_id=user_id, title="Shipped search", entry_date=date(2026, 1, 1), content_hash="h"
        )
        session.add(entry)
        await session.flush()
        session.add(WorklogSource(worklog_id=entry.id, source_id=source.id))
        tag = Tag(user_id=user_id, label="backend")
        session.add(tag)
        await session.flush()
        session.add(WorklogTag(worklog_id=entry.id, tag_id=tag.id))

        bullet = Bulletpoint(user_id=user_id, text="Led the migration", content_hash="h")
        session.add(bullet)
        await session.flush()
        session.add(BulletSource(bullet_id=bullet.id, source_id=source.id))
        session.add(BulletWorklog(bullet_id=bullet.id, worklog_id=entry.id))

        resume = Resume(
            user_id=user_id,
            kind=ResumeKind.LIVING,
            status=ResumeStatus.DRAFT,
            title="Backend",
            schema_version=1,
            revision=1,
            document={"sections": []},
        )
        session.add(resume)
        await session.flush()
        session.add(
            ResumeRevision(
                resume_id=resume.id,
                revision_no=1,
                document={"sections": []},
                schema_version=1,
                pdf_object_key="r2/backend.pdf",
            )
        )
        session.add(ResumeBulletRef(resume_id=resume.id, bullet_id=bullet.id))

        graph = _Graph(source.id, entry.id, bullet.id, resume.id)

    repo = None
    async with sessionmaker() as session, transaction(session):
        repo = SqlAlchemyEmbeddingRepository(session)
        for kind, item_id in (
            (EmbedItemKind.WORKLOG, graph.worklog_id),
            (EmbedItemKind.SOURCE, graph.source_id),
            (EmbedItemKind.BULLET, graph.bullet_id),
        ):
            await repo.upsert(
                user_id=user_id,
                kind=kind,
                item_id=item_id,
                content_hash="h",
                vector=_VECTOR,
                model=EMBEDDING_MODEL,
            )
    return graph


async def _count(session: AsyncSession, statement: Select[tuple[int]]) -> int:
    return int(await session.scalar(statement) or 0)


async def test_permanent_delete_source_cascades_edges_and_purges_its_vector(
    migrated_url: str,
) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "lc-source@example.com")
        graph = await _seed_graph(sessionmaker, user_id)

        async with sessionmaker() as session:
            receipt = await _service(session).permanently_delete_source(
                str(user_id), graph.source_id, _HUMAN, confirm=True
            )

        async with sessionmaker() as session:
            sources = await _count(
                session,
                select(func.count()).select_from(Source).where(Source.id == graph.source_id),
            )
            roles = await _count(
                session,
                select(func.count()).select_from(Role).where(Role.source_id == graph.source_id),
            )
            worklog_edges = await _count(
                session,
                select(func.count())
                .select_from(WorklogSource)
                .where(WorklogSource.source_id == graph.source_id),
            )
            bullet_edges = await _count(
                session,
                select(func.count())
                .select_from(BulletSource)
                .where(BulletSource.source_id == graph.source_id),
            )
            worklog_survives = await _count(
                session,
                select(func.count())
                .select_from(WorklogEntry)
                .where(WorklogEntry.id == graph.worklog_id),
            )
            bullet_survives = await _count(
                session,
                select(func.count())
                .select_from(Bulletpoint)
                .where(Bulletpoint.id == graph.bullet_id),
            )
            vector = await _count(
                session,
                select(func.count())
                .select_from(Embedding)
                .where(
                    Embedding.item_kind == EmbedItemKind.SOURCE,
                    Embedding.item_id == graph.source_id,
                ),
            )
            delete_audit = await _count(
                session,
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.entity_type == "source",
                    AuditLog.entity_id == graph.source_id,
                    AuditLog.action == "delete",
                ),
            )
    finally:
        await engine.dispose()

    assert receipt.embedding_purged is True
    assert sources == 0
    assert roles == 0  # subtype cascaded
    assert worklog_edges == 0 and bullet_edges == 0  # join rows cascaded
    assert worklog_survives == 1 and bullet_survives == 1  # siblings keep, lose the edge
    assert vector == 0  # embeddings row explicitly purged
    assert delete_audit == 1  # the recovery-net audit row survives the delete


async def test_permanent_delete_worklog_cascades_edges_and_purges_its_vector(
    migrated_url: str,
) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "lc-worklog@example.com")
        graph = await _seed_graph(sessionmaker, user_id)

        async with sessionmaker() as session:
            await _service(session).permanently_delete_worklog(
                str(user_id), graph.worklog_id, _HUMAN, confirm=True
            )

        async with sessionmaker() as session:
            worklog = await _count(
                session,
                select(func.count())
                .select_from(WorklogEntry)
                .where(WorklogEntry.id == graph.worklog_id),
            )
            worklog_edges = await _count(
                session,
                select(func.count())
                .select_from(WorklogSource)
                .where(WorklogSource.worklog_id == graph.worklog_id),
            )
            bullet_worklog_edges = await _count(
                session,
                select(func.count())
                .select_from(BulletWorklog)
                .where(BulletWorklog.worklog_id == graph.worklog_id),
            )
            bullet_survives = await _count(
                session,
                select(func.count())
                .select_from(Bulletpoint)
                .where(Bulletpoint.id == graph.bullet_id),
            )
            vector = await _count(
                session,
                select(func.count())
                .select_from(Embedding)
                .where(
                    Embedding.item_kind == EmbedItemKind.WORKLOG,
                    Embedding.item_id == graph.worklog_id,
                ),
            )
    finally:
        await engine.dispose()

    assert worklog == 0
    assert worklog_edges == 0 and bullet_worklog_edges == 0
    assert bullet_survives == 1
    assert vector == 0


async def test_permanent_delete_bullet_cascades_refs_and_purges_its_vector(
    migrated_url: str,
) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "lc-bullet@example.com")
        graph = await _seed_graph(sessionmaker, user_id)

        async with sessionmaker() as session:
            await _service(session).permanently_delete_bullet(
                str(user_id), graph.bullet_id, _HUMAN, confirm=True
            )

        async with sessionmaker() as session:
            bullet = await _count(
                session,
                select(func.count())
                .select_from(Bulletpoint)
                .where(Bulletpoint.id == graph.bullet_id),
            )
            refs = await _count(
                session,
                select(func.count())
                .select_from(ResumeBulletRef)
                .where(ResumeBulletRef.bullet_id == graph.bullet_id),
            )
            resume_survives = await _count(
                session,
                select(func.count()).select_from(Resume).where(Resume.id == graph.resume_id),
            )
            vector = await _count(
                session,
                select(func.count())
                .select_from(Embedding)
                .where(
                    Embedding.item_kind == EmbedItemKind.BULLET,
                    Embedding.item_id == graph.bullet_id,
                ),
            )
    finally:
        await engine.dispose()

    assert bullet == 0
    assert refs == 0  # resume_bullet_ref cascaded
    assert resume_survives == 1  # the resume keeps; its ref index dropped the bullet
    assert vector == 0


async def test_permanent_delete_resume_removes_revisions_but_keeps_the_finalize_audit(
    migrated_url: str,
) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "lc-resume@example.com")
        graph = await _seed_graph(sessionmaker, user_id)
        # A prior finalize audit row (the retention record of what was sent).
        async with sessionmaker() as session, transaction(session):
            session.add(
                AuditLog(
                    user_id=user_id,
                    actor_type=ActorType.HUMAN,
                    entity_type="resume",
                    entity_id=graph.resume_id,
                    action="finalize",
                    summary="Finalized Backend",
                )
            )

        async with sessionmaker() as session:
            await _service(session).permanently_delete_resume(
                str(user_id), graph.resume_id, _HUMAN, confirm=True
            )

        async with sessionmaker() as session:
            resume = await _count(
                session,
                select(func.count()).select_from(Resume).where(Resume.id == graph.resume_id),
            )
            revisions = await _count(
                session,
                select(func.count())
                .select_from(ResumeRevision)
                .where(ResumeRevision.resume_id == graph.resume_id),
            )
            finalize_audit = await _count(
                session,
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.user_id == user_id,
                    AuditLog.entity_id == graph.resume_id,
                    AuditLog.action == "finalize",
                ),
            )
            delete_audit = await _count(
                session,
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.user_id == user_id,
                    AuditLog.entity_id == graph.resume_id,
                    AuditLog.action == "delete",
                ),
            )
    finally:
        await engine.dispose()

    assert resume == 0
    assert revisions == 0  # resume_revisions cascaded with the resume
    assert finalize_audit == 1  # the finalize record is retained (no FK to the resume)
    assert delete_audit == 1


async def test_account_delete_cascades_all_records_and_revokes_agents(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "lc-account@example.com")
        await _seed_graph(sessionmaker, user_id)
        expires = datetime.now(UTC) + timedelta(days=1)
        async with sessionmaker() as session, transaction(session):
            session.add(
                OAuthGrant(
                    id="grant-acct", user_id=str(user_id), client_id="client-1", scope="full"
                )
            )
            session.add(
                OAuthRefreshToken(
                    token_hash="hash-acct",
                    grant_id="grant-acct",
                    client_id="client-1",
                    user_id=str(user_id),
                    scope="full",
                    resource="https://mcp.example",
                    expires_at=expires,
                )
            )
            session.add(RevokedSession(sid="sid-acct", user_id=user_id, expires_at=expires))

        async with sessionmaker() as session:
            receipt = await _service(session).delete_account(str(user_id), confirm=True)

        async with sessionmaker() as session:
            users = await _count(
                session, select(func.count()).select_from(User).where(User.id == user_id)
            )
            worklog = await _count(
                session,
                select(func.count())
                .select_from(WorklogEntry)
                .where(WorklogEntry.user_id == user_id),
            )
            sources = await _count(
                session, select(func.count()).select_from(Source).where(Source.user_id == user_id)
            )
            bullets = await _count(
                session,
                select(func.count()).select_from(Bulletpoint).where(Bulletpoint.user_id == user_id),
            )
            resumes = await _count(
                session, select(func.count()).select_from(Resume).where(Resume.user_id == user_id)
            )
            vectors = await _count(
                session,
                select(func.count()).select_from(Embedding).where(Embedding.user_id == user_id),
            )
            grants = await _count(
                session,
                select(func.count())
                .select_from(OAuthGrant)
                .where(OAuthGrant.user_id == str(user_id)),
            )
            tokens = await _count(
                session,
                select(func.count())
                .select_from(OAuthRefreshToken)
                .where(OAuthRefreshToken.user_id == str(user_id)),
            )
            blacklist = await _count(
                session,
                select(func.count())
                .select_from(RevokedSession)
                .where(RevokedSession.user_id == user_id),
            )
    finally:
        await engine.dispose()

    assert receipt.deleted is True
    assert receipt.revoked_agent_count == 1
    assert users == 0
    assert worklog == 0 and sources == 0 and bullets == 0 and resumes == 0
    assert vectors == 0  # embeddings removed via the user_id cascade
    assert grants == 0 and tokens == 0  # the OAuth grant chain (no FK) explicitly revoked
    assert blacklist == 0


async def test_export_returns_only_the_owners_records(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        owner = await _insert_user(sessionmaker, "lc-export-owner@example.com")
        other = await _insert_user(sessionmaker, "lc-export-other@example.com")
        mine = await _seed_graph(sessionmaker, owner)
        theirs = await _seed_graph(sessionmaker, other)

        async with sessionmaker() as session:
            archive = await _service(session).export_data(str(owner))
    finally:
        await engine.dispose()

    assert archive["account"]["email"] == "lc-export-owner@example.com"
    source_ids = {row["id"] for row in archive["sources"]}
    worklog_ids = {row["id"] for row in archive["worklog_entries"]}
    bullet_ids = {row["id"] for row in archive["bulletpoints"]}
    resume_ids = {row["id"] for row in archive["resumes"]}
    # The owner's records are present with their edges resolved through real SQL.
    assert mine.source_id in source_ids
    assert archive["worklog_entries"][0]["tags"] == ["backend"]
    assert archive["worklog_entries"][0]["source_ids"] == [mine.source_id]
    assert archive["bulletpoints"][0]["source_ids"] == [mine.source_id]
    assert archive["bulletpoints"][0]["worklog_ids"] == [mine.worklog_id]
    # The other account's records are excluded by construction (every read is
    # scoped to the owner's user id).
    assert theirs.source_id not in source_ids
    assert theirs.worklog_id not in worklog_ids
    assert theirs.bullet_id not in bullet_ids
    assert theirs.resume_id not in resume_ids
