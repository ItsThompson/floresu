"""Sociable tests for :class:`LifecycleService` over in-memory doubles.

The real service, the real write-event seam (with a capturing consumer), the
shared in-memory embedding repository, and the in-memory lifecycle/export
repositories. These cover the confirmation gate, the 404 mapping, the deletion
receipts, the vector purge (present for embeddable kinds, absent for a resume),
the single ``DELETE`` audit event, account revocation, and the export assembly.
Database-enforced cascade is proven in the integration suite.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from floresu.core.actor import Actor, ActorType
from floresu.core.errors import NotFound, Unauthorized, Validation
from floresu.core.events import Action
from floresu.embedding.config import EMBEDDING_MODEL, EmbedItemKind
from floresu.lifecycle.service import LifecycleService
from floresu.profile.models import Source, SourceKind
from tests.embedding_fakes import InMemoryEmbeddingRepository
from tests.lifecycle_fakes import (
    InMemoryExportRepository,
    InMemoryLifecycleRepository,
    build_account,
)
from tests.support.fakes import CapturingWriteEventPublisher, FakeSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.core.events import WriteEvent

_USER = "1"
_PK = 1
_HUMAN = Actor(type=ActorType.HUMAN)


def _service(
    repo: InMemoryLifecycleRepository | None = None,
    export_repo: InMemoryExportRepository | None = None,
    embeddings: InMemoryEmbeddingRepository | None = None,
) -> tuple[
    LifecycleService, InMemoryLifecycleRepository, InMemoryEmbeddingRepository, list[WriteEvent]
]:
    repo = repo or InMemoryLifecycleRepository()
    export_repo = export_repo or InMemoryExportRepository(account=build_account(_PK))
    embeddings = embeddings or InMemoryEmbeddingRepository()
    publisher = CapturingWriteEventPublisher()
    captured = publisher.captured
    service = LifecycleService(
        cast("AsyncSession", FakeSession()), repo, export_repo, embeddings, publisher
    )
    return service, repo, embeddings, captured


async def _seed_vector(
    embeddings: InMemoryEmbeddingRepository, kind: EmbedItemKind, id_: int
) -> None:
    await embeddings.upsert(
        user_id=_PK, kind=kind, item_id=id_, content_hash="h", vector=[0.0], model=EMBEDDING_MODEL
    )


async def test_permanent_delete_worklog_removes_purges_and_audits() -> None:
    repo = InMemoryLifecycleRepository()
    repo.seed_worklog(_PK, 5, "Shipped search")
    service, _, embeddings, captured = _service(repo=repo)
    await _seed_vector(embeddings, EmbedItemKind.WORKLOG, 5)

    receipt = await service.permanently_delete_worklog(_USER, 5, _HUMAN, confirm=True)

    assert receipt.entity_type == "worklog"
    assert receipt.entity_id == 5
    assert receipt.embedding_purged is True
    assert (_PK, 5) not in repo.worklog
    assert await embeddings.get(EmbedItemKind.WORKLOG, 5) is None
    assert captured[-1].action is Action.DELETE
    assert captured[-1].entity_type == "worklog"
    assert captured[-1].entity_id == 5
    assert captured[-1].actor.type is ActorType.HUMAN
    assert (captured[-1].metadata or {}).get("permanent") is True


async def test_permanent_delete_source_uses_kind_and_label_in_summary() -> None:
    repo = InMemoryLifecycleRepository()
    repo.seed_source(_PK, 7, "role", "Staff Engineer at Acme")
    service, _, embeddings, captured = _service(repo=repo)
    await _seed_vector(embeddings, EmbedItemKind.SOURCE, 7)

    receipt = await service.permanently_delete_source(_USER, 7, _HUMAN, confirm=True)

    assert receipt.embedding_purged is True
    assert await embeddings.get(EmbedItemKind.SOURCE, 7) is None
    assert "role" in (captured[-1].summary or "")
    assert "Staff Engineer at Acme" in (captured[-1].summary or "")


async def test_permanent_delete_bullet_purges_its_vector() -> None:
    repo = InMemoryLifecycleRepository()
    repo.seed_bullet(_PK, 3, "Led the migration")
    service, _, embeddings, captured = _service(repo=repo)
    await _seed_vector(embeddings, EmbedItemKind.BULLET, 3)

    receipt = await service.permanently_delete_bullet(_USER, 3, _HUMAN, confirm=True)

    assert receipt.embedding_purged is True
    assert await embeddings.get(EmbedItemKind.BULLET, 3) is None
    assert captured[-1].entity_type == "bullet"


async def test_permanent_delete_resume_does_not_purge_a_vector() -> None:
    repo = InMemoryLifecycleRepository()
    repo.seed_resume(_PK, 9, "Backend Engineer")
    service, _, _, captured = _service(repo=repo)

    receipt = await service.permanently_delete_resume(_USER, 9, _HUMAN, confirm=True)

    assert receipt.entity_type == "resume"
    assert receipt.embedding_purged is False
    assert captured[-1].action is Action.DELETE
    assert captured[-1].entity_type == "resume"


@pytest.mark.parametrize(
    "call",
    [
        lambda s: s.permanently_delete_worklog(_USER, 5, _HUMAN, confirm=False),
        lambda s: s.permanently_delete_source(_USER, 5, _HUMAN, confirm=False),
        lambda s: s.permanently_delete_bullet(_USER, 5, _HUMAN, confirm=False),
        lambda s: s.permanently_delete_resume(_USER, 5, _HUMAN, confirm=False),
    ],
)
async def test_delete_without_confirmation_is_rejected(call) -> None:  # type: ignore[no-untyped-def]
    repo = InMemoryLifecycleRepository()
    repo.seed_worklog(_PK, 5, "x")
    repo.seed_source(_PK, 5, "role", "x")
    repo.seed_bullet(_PK, 5, "x")
    repo.seed_resume(_PK, 5, "x")
    service, _, _, captured = _service(repo=repo)

    with pytest.raises(Validation):
        await call(service)
    # The confirmation gate rejects before any delete or audit publish.
    assert captured == []
    assert (_PK, 5) in repo.worklog


async def test_delete_missing_entity_is_not_found() -> None:
    service, _, _, _ = _service()
    with pytest.raises(NotFound):
        await service.permanently_delete_worklog(_USER, 404, _HUMAN, confirm=True)


async def test_delete_account_revokes_agents_and_deletes_the_user_without_auditing() -> None:
    repo = InMemoryLifecycleRepository()
    repo.seed_agents(_PK, count=2)
    service, _, _, captured = _service(repo=repo)

    receipt = await service.delete_account(_USER, confirm=True)

    assert receipt.deleted is True
    assert receipt.revoked_agent_count == 2
    assert repo.revoked_agents == [_USER]
    assert _PK in repo.cleared_blacklist
    assert _PK not in repo.users
    # Account deletion is not audited: the audit rows cascade away with the account.
    assert captured == []


async def test_delete_account_requires_confirmation() -> None:
    repo = InMemoryLifecycleRepository()
    repo.seed_agents(_PK, count=1)
    service, _, _, _ = _service(repo=repo)

    with pytest.raises(Validation):
        await service.delete_account(_USER, confirm=False)
    assert _PK in repo.users


async def test_delete_account_of_a_missing_user_is_a_stale_session() -> None:
    service, _, _, _ = _service()  # repo has no seeded user
    with pytest.raises(Unauthorized):
        await service.delete_account(_USER, confirm=True)


async def test_export_assembles_the_account_records() -> None:
    export_repo = InMemoryExportRepository(account=build_account(_PK, email="me@example.com"))
    service, _, _, _ = _service(export_repo=export_repo)

    archive = await service.export_data(_USER)

    assert archive["account"]["email"] == "me@example.com"
    assert archive["schema_version"] == 1
    assert archive["exported_at"] is not None
    # Every record section is present (empty here) so an importer sees the shape.
    for section in ("worklog_entries", "sources", "bulletpoints", "resumes", "job_applications"):
        assert section in archive


async def test_export_of_a_missing_account_is_a_stale_session() -> None:
    export_repo = InMemoryExportRepository(account=None)
    service, _, _, _ = _service(export_repo=export_repo)
    with pytest.raises(Unauthorized):
        await service.export_data(_USER)


async def test_export_omits_a_source_missing_its_subtype_detail() -> None:
    # A base source with no resolved subtype detail is unreachable in production
    # (composite FK), but the export must omit it rather than export it half-formed.
    export_repo = InMemoryExportRepository(account=build_account(_PK))
    source = Source(user_id=_PK, kind=SourceKind.ROLE, display_label="Orphan", sort_order=0)
    source.id = 42
    export_repo.source_rows = [source]  # no matching source_detail_map entry
    service, _, _, _ = _service(export_repo=export_repo)

    archive = await service.export_data(_USER)

    assert archive["sources"] == []


async def test_a_non_numeric_identity_is_rejected() -> None:
    service, _, _, _ = _service()
    with pytest.raises(Unauthorized) as excinfo:
        await service.permanently_delete_worklog("not-an-int", 1, _HUMAN, confirm=True)
    # The migrated cast rejects with the canonical wording, not the divergent
    # ``_STALE_SESSION`` message the deleted-account path still uses.
    assert excinfo.value.detail == "Session is invalid or expired."
