"""End-to-end skills + identity-variant tests against real Postgres.

Runs the real services over their SQLAlchemy repositories and the composed
write-event publisher (audit as its transactional consumer). For skills it proves
the audited create, the computed usage count against real worklog tags (including
that archived worklog entries are excluded and that a rename onto an existing name
conflicts via the unique constraint), and reorder. For identity variants it proves
the first-variant default, the same-transaction default flip (exactly one default
persisted), and that the default cannot be archived until another is promoted.
"""

from __future__ import annotations

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
from floresu.core.errors import Conflict
from floresu.profile.skills.models import Skill
from floresu.profile.skills.repository import SqlAlchemySkillRepository
from floresu.profile.skills.schemas import SkillReorderRequest
from floresu.profile.skills.service import SkillService
from floresu.profile.variants.models import IdentityVariant
from floresu.profile.variants.repository import SqlAlchemyIdentityVariantRepository
from floresu.profile.variants.service import IdentityVariantService
from floresu.worklog.repository import SqlAlchemyWorklogRepository
from floresu.worklog.service import WorklogService
from tests.skills_fakes import build_skill_write
from tests.variants_fakes import build_variant_write
from tests.worklog_fakes import build_worklog_write

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


async def _insert_user(sessionmaker: async_sessionmaker[AsyncSession], email: str) -> int:
    async with sessionmaker() as session, transaction(session):
        user = User(email=email, password_hash="x")
        session.add(user)
        await session.flush()
        return user.id


def _skills(session: AsyncSession) -> SkillService:
    return SkillService(session, SqlAlchemySkillRepository(session), build_write_event_publisher())


def _variants(session: AsyncSession) -> IdentityVariantService:
    return IdentityVariantService(
        session, SqlAlchemyIdentityVariantRepository(session), build_write_event_publisher()
    )


def _worklog(session: AsyncSession) -> WorklogService:
    return WorklogService(
        session, SqlAlchemyWorklogRepository(session), build_write_event_publisher()
    )


async def test_create_skill_writes_the_row_and_audit(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "skill-create@example.com")
        async with sessionmaker() as session:
            skill = await _skills(session).create(str(user_id), _HUMAN, build_skill_write())

        async with sessionmaker() as session:
            skills = await session.scalar(
                select(func.count()).select_from(Skill).where(Skill.user_id == user_id)
            )
            audit = (
                (
                    await session.execute(
                        select(AuditLog).where(
                            AuditLog.entity_type == "skill", AuditLog.user_id == user_id
                        )
                    )
                )
                .scalars()
                .all()
            )
    finally:
        await engine.dispose()

    assert skills == 1
    assert skill.sort_order == 0
    assert len(audit) == 1
    assert audit[0].action == "create"
    assert audit[0].entity_id == skill.id
    assert audit[0].actor_type is ActorType.HUMAN


async def test_usage_count_matches_worklog_tags_and_excludes_archived(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "skill-usage@example.com")
        # Two worklog entries tagged "Python"; then curate the "Python" skill.
        async with sessionmaker() as session:
            first = await _worklog(session).create(
                str(user_id), _HUMAN, build_worklog_write(title="A", tags=["Python"])
            )
        async with sessionmaker() as session:
            await _worklog(session).create(
                str(user_id), _HUMAN, build_worklog_write(title="B", tags=["Python", "ml"])
            )
        async with sessionmaker() as session:
            created = await _skills(session).create(
                str(user_id), _HUMAN, build_skill_write(name="Python")
            )
        # The curated skill's usage reflects the two tagged entries.
        assert created.usage_count == 2

        # Archiving one tagged entry drops it from the count (active corpus only).
        async with sessionmaker() as session:
            await _worklog(session).archive(str(user_id), first.id, _HUMAN)
        async with sessionmaker() as session:
            refetched = await _skills(session).get(str(user_id), created.id)
    finally:
        await engine.dispose()

    assert refetched.usage_count == 1


async def test_rename_onto_an_existing_name_conflicts(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "skill-rename@example.com")
        async with sessionmaker() as session:
            first = await _skills(session).create(
                str(user_id), _HUMAN, build_skill_write(name="Go")
            )
        async with sessionmaker() as session:
            await _skills(session).create(str(user_id), _HUMAN, build_skill_write(name="Rust"))
        # Renaming "Go" -> "Rust" breaches uq_skills_user_id; the constraint fires at
        # commit and the service maps it to a recoverable Conflict, not a 500.
        with pytest.raises(Conflict):
            async with sessionmaker() as session:
                await _skills(session).update(
                    str(user_id), first.id, _HUMAN, build_skill_write(name="Rust")
                )
    finally:
        await engine.dispose()


async def test_reorder_persists_sort_order(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "skill-reorder@example.com")
        ids: list[int] = []
        for name in ("A", "B", "C"):
            async with sessionmaker() as session:
                created = await _skills(session).create(
                    str(user_id), _HUMAN, build_skill_write(name=name)
                )
                ids.append(created.id)
        new_order = [ids[2], ids[0], ids[1]]
        async with sessionmaker() as session:
            await _skills(session).reorder(
                str(user_id), _HUMAN, SkillReorderRequest(skill_ids=new_order)
            )
        async with sessionmaker() as session:
            listed = await _skills(session).list_skills(str(user_id))
    finally:
        await engine.dispose()

    assert [s.id for s in listed] == new_order
    assert [s.sort_order for s in listed] == [0, 1, 2]


async def test_list_reflects_archive_and_the_empty_usage_read(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "skill-list@example.com")
        async with sessionmaker() as session:
            created = await _skills(session).create(str(user_id), _HUMAN, build_skill_write())
        async with sessionmaker() as session:
            await _skills(session).archive(str(user_id), created.id, _HUMAN)
        async with sessionmaker() as session:
            # Active list is empty (usage computed over an empty name set); the
            # archived skill is visible only with include_archived.
            active = await _skills(session).list_skills(str(user_id))
            including = await _skills(session).list_skills(str(user_id), include_archived=True)
    finally:
        await engine.dispose()

    assert active == []
    assert [s.id for s in including] == [created.id]
    assert including[0].usage_count == 0


async def test_first_variant_is_default_and_promotion_flips_in_one_transaction(
    migrated_url: str,
) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "variant-default@example.com")
        async with sessionmaker() as session:
            first = await _variants(session).create(
                str(user_id), _HUMAN, build_variant_write(label="Personal")
            )
        async with sessionmaker() as session:
            second = await _variants(session).create(
                str(user_id), _HUMAN, build_variant_write(label="Academic")
            )
        assert first.is_default is True
        assert second.is_default is False

        # Promote the second; the previous default must flip off in the same txn.
        async with sessionmaker() as session:
            await _variants(session).update(
                str(user_id),
                second.id,
                _HUMAN,
                build_variant_write(label="Academic", is_default=True),
            )
        async with sessionmaker() as session:
            default_count = await session.scalar(
                select(func.count())
                .select_from(IdentityVariant)
                .where(IdentityVariant.user_id == user_id, IdentityVariant.is_default.is_(True))
            )
            first_row = await session.get(IdentityVariant, first.id)
            second_row = await session.get(IdentityVariant, second.id)
    finally:
        await engine.dispose()

    # Exactly one default persisted, and it is the promoted variant.
    assert default_count == 1
    assert first_row is not None and first_row.is_default is False
    assert second_row is not None and second_row.is_default is True


async def test_list_variants_reflects_archive(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "variant-list@example.com")
        async with sessionmaker() as session:
            await _variants(session).create(
                str(user_id), _HUMAN, build_variant_write(label="Personal")
            )
        async with sessionmaker() as session:
            second = await _variants(session).create(
                str(user_id), _HUMAN, build_variant_write(label="Academic")
            )
        async with sessionmaker() as session:
            await _variants(session).archive(str(user_id), second.id, _HUMAN)
        async with sessionmaker() as session:
            active = await _variants(session).list_variants(str(user_id))
            including = await _variants(session).list_variants(str(user_id), include_archived=True)
    finally:
        await engine.dispose()

    # Active list drops the archived variant; include_archived shows both (by label).
    assert [v.label for v in active] == ["Personal"]
    assert [v.label for v in including] == ["Academic", "Personal"]


async def test_default_variant_cannot_be_archived_until_another_is_default(
    migrated_url: str,
) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "variant-archive@example.com")
        async with sessionmaker() as session:
            first = await _variants(session).create(
                str(user_id), _HUMAN, build_variant_write(label="Personal")
            )
        async with sessionmaker() as session:
            second = await _variants(session).create(
                str(user_id), _HUMAN, build_variant_write(label="Academic")
            )
        # first is default; archiving it is blocked.
        with pytest.raises(Conflict):
            async with sessionmaker() as session:
                await _variants(session).archive(str(user_id), first.id, _HUMAN)
        # Promote second, then first archives cleanly and audits.
        async with sessionmaker() as session:
            await _variants(session).update(
                str(user_id),
                second.id,
                _HUMAN,
                build_variant_write(label="Academic", is_default=True),
            )
        async with sessionmaker() as session:
            archived = await _variants(session).archive(str(user_id), first.id, _HUMAN)
        async with sessionmaker() as session:
            actions = (
                (
                    await session.execute(
                        select(AuditLog.action)
                        .where(
                            AuditLog.entity_type == "identity_variant",
                            AuditLog.entity_id == first.id,
                        )
                        .order_by(AuditLog.id)
                    )
                )
                .scalars()
                .all()
            )
    finally:
        await engine.dispose()

    assert archived.archived_at is not None
    assert actions == ["create", "archive"]
