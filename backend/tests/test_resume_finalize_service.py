"""Sociable tests for the resume finalize routine: the highest-density target.

The real :class:`ResumeFinalizeService` runs over in-memory doubles standing in only
at true external boundaries (Postgres via the in-memory resume + job-application
repos, R2 via the fake object store, Typst via the fake compiler) with the real render
module, bullet-text resolver, identity resolver, and write-event seam. The assertions
pin the finalize contract: every reference resolves to inline read-only text (zero
``library_ref`` remain), the identity is snapshotted inline, the frozen PDF is stored
and its key recorded on the appended revision, the resume drops out of "used in N", a
linked application is submitted idempotently (a standalone draft is not), the write is
audited, and the guards reject a living or already-finalized resume and a dangling ref.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from floresu.core.actor import Actor, ActorType
from floresu.core.errors import Conflict, Validation
from floresu.core.events import Action, WriteEvent
from floresu.rendering.module import RenderModule
from floresu.resumes.document import (
    LibraryRefItem,
    LocalItem,
    ResumeDocument,
    ResumeHeader,
    ResumeSection,
    SectionKind,
)
from floresu.resumes.finalize import ResumeFinalizeService
from floresu.resumes.models import (
    JobApplicationStatus,
    Resume,
    ResumeKind,
    ResumeStatus,
)
from tests.jobapps_fakes import FIXED_NOW, InMemoryJobApplicationRepository, build_application
from tests.rendering_fakes import FakeTypstCompiler, InMemoryIdentityResolver, build_snapshot
from tests.resumes_fakes import (
    InMemoryBulletTextResolver,
    InMemoryResumeRepository,
)
from tests.storage_fakes import FakeObjectStore
from tests.support.fakes import CapturingWriteEventPublisher, FakeSession

_HUMAN = Actor(type=ActorType.HUMAN)
_USER = "1"
_USER_PK = 1
_BULLET_ID = 5


def _draft_document(*, variant_id: int | None = 9) -> ResumeDocument:
    """An application-draft document: a canonical reference plus a net-new inline item."""
    return ResumeDocument(
        schema_version=1,
        header=ResumeHeader(identity_variant_id=variant_id),
        template_id="classic",
        sections=[
            ResumeSection(
                id="s-work",
                kind=SectionKind.WORK,
                title="Experience",
                item_order=["i-ref", "i-local"],
                items={
                    "i-ref": LibraryRefItem(id="i-ref", bullet_id=_BULLET_ID),
                    "i-local": LocalItem(id="i-local", text="Wrote the onboarding guide."),
                },
            )
        ],
    )


class _Harness:
    def __init__(self) -> None:
        self.repo = InMemoryResumeRepository()
        self.bullets = InMemoryBulletTextResolver()
        self.identity = InMemoryIdentityResolver()
        self.store = FakeObjectStore()
        self.job_apps = InMemoryJobApplicationRepository()
        self.render = RenderModule(FakeTypstCompiler(), templates_dir=Path("/tmpl"))
        self.publisher = CapturingWriteEventPublisher()
        self.captured = self.publisher.captured
        self.service = ResumeFinalizeService(
            FakeSession(),  # type: ignore[arg-type]
            self.repo,
            self.bullets,
            self.identity,
            self.render,
            self.store,
            self.job_apps,
            self.publisher,
            clock=lambda: FIXED_NOW,
        )

    async def seed_resume(
        self,
        *,
        kind: ResumeKind = ResumeKind.APPLICATION,
        status: ResumeStatus = ResumeStatus.DRAFT,
        document: ResumeDocument | None = None,
        job_application_id: int | None = None,
    ) -> Resume:
        resume = Resume(
            user_id=_USER_PK,
            kind=kind,
            status=status,
            title="Backend Engineer",
            schema_version=1,
            revision=1,
            document=(document or _draft_document()).model_dump(mode="json"),
            job_application_id=job_application_id,
            created_at=FIXED_NOW,
            updated_at=FIXED_NOW,
        )
        await self.repo.add(resume)
        return resume


def _events(captured: list[WriteEvent], entity_type: str) -> list[WriteEvent]:
    return [event for event in captured if event.entity_type == entity_type]


@pytest.mark.asyncio
async def test_finalize_inlines_every_reference_and_leaves_zero_library_refs() -> None:
    harness = _Harness()
    harness.bullets.own_bullet(_USER_PK, _BULLET_ID, "Shipped the pipeline.")
    harness.identity.own_variant(_USER_PK, 9, build_snapshot(full_name="Grace Hopper"))
    resume = await harness.seed_resume()

    await harness.service.finalize(_USER, resume.id, _HUMAN)

    document = ResumeDocument.model_validate(resume.document)
    items = document.sections[0].items
    assert all(isinstance(item, LocalItem) for item in items.values())
    # The reference resolved to its canonical text once, retaining provenance.
    ref = items["i-ref"]
    assert isinstance(ref, LocalItem)
    assert ref.text == "Shipped the pipeline."
    assert ref.forked_from_bullet_id == _BULLET_ID
    assert document.header.identity_snapshot is not None
    assert document.header.identity_snapshot.full_name == "Grace Hopper"
    assert document.header.identity_variant_id is None


@pytest.mark.asyncio
async def test_finalize_stores_the_pdf_and_records_the_key_on_a_snapshot() -> None:
    harness = _Harness()
    harness.bullets.own_bullet(_USER_PK, _BULLET_ID, "Shipped the pipeline.")
    resume = await harness.seed_resume()

    result = await harness.service.finalize(_USER, resume.id, _HUMAN)

    assert result.status is ResumeStatus.FINALIZED
    assert result.revision_no == 2
    key = f"u/1/r/{resume.id}/rev/2.pdf"
    assert result.pdf_object_key == key
    assert key in harness.store.objects
    snapshot = harness.repo.revision(resume.id, 2)
    assert snapshot is not None
    assert snapshot.pdf_object_key == key
    snapshot_doc = ResumeDocument.model_validate(snapshot.document)
    assert all(
        item.kind == "local" for section in snapshot_doc.sections for item in section.items.values()
    )


@pytest.mark.asyncio
async def test_finalize_flips_status_and_drops_out_of_used_in_n() -> None:
    harness = _Harness()
    harness.bullets.own_bullet(_USER_PK, _BULLET_ID, "Shipped the pipeline.")
    resume = await harness.seed_resume()
    # This resume and a second (living) resume both reference the bullet: used-in 2.
    await harness.repo.set_bullet_refs(resume.id, [_BULLET_ID])
    await harness.repo.set_bullet_refs(999, [_BULLET_ID])
    assert await harness.repo.used_in_count(_BULLET_ID) == 2
    assert await harness.repo.used_in_counts([_BULLET_ID]) == {_BULLET_ID: 2}

    await harness.service.finalize(_USER, resume.id, _HUMAN)

    assert resume.status is ResumeStatus.FINALIZED
    # The finalized resume dropped its ref; only the live reference remains.
    assert await harness.repo.used_in_count(_BULLET_ID) == 1
    assert await harness.repo.used_in_counts([_BULLET_ID]) == {_BULLET_ID: 1}
    assert harness.repo.bullet_refs(resume.id) == []


@pytest.mark.asyncio
async def test_finalize_submits_a_linked_application_and_audits_both_writes() -> None:
    harness = _Harness()
    harness.bullets.own_bullet(_USER_PK, _BULLET_ID, "Shipped the pipeline.")
    application = harness.job_apps.seed(build_application())
    resume = await harness.seed_resume(job_application_id=application.id)

    await harness.service.finalize(_USER, resume.id, _HUMAN)

    assert application.status is JobApplicationStatus.SUBMITTED
    resume_events = _events(harness.captured, "resume")
    application_events = _events(harness.captured, "job_application")
    assert [event.action for event in resume_events] == [Action.FINALIZE]
    assert [event.action for event in application_events] == [Action.UPDATE]


@pytest.mark.asyncio
async def test_finalize_of_a_standalone_draft_succeeds_with_no_status_sync() -> None:
    harness = _Harness()
    harness.bullets.own_bullet(_USER_PK, _BULLET_ID, "Shipped the pipeline.")
    resume = await harness.seed_resume(job_application_id=None)

    result = await harness.service.finalize(_USER, resume.id, _HUMAN)

    assert result.status is ResumeStatus.FINALIZED
    assert _events(harness.captured, "job_application") == []


@pytest.mark.asyncio
async def test_finalize_is_idempotent_on_an_already_submitted_application() -> None:
    harness = _Harness()
    harness.bullets.own_bullet(_USER_PK, _BULLET_ID, "Shipped the pipeline.")
    application = harness.job_apps.seed(build_application(status=JobApplicationStatus.SUBMITTED))
    resume = await harness.seed_resume(job_application_id=application.id)

    await harness.service.finalize(_USER, resume.id, _HUMAN)

    # Already submitted: no second application event is published.
    assert _events(harness.captured, "job_application") == []


@pytest.mark.asyncio
async def test_finalize_rejects_a_living_resume() -> None:
    harness = _Harness()
    resume = await harness.seed_resume(kind=ResumeKind.LIVING, job_application_id=None)

    with pytest.raises(Conflict):
        await harness.service.finalize(_USER, resume.id, _HUMAN)


@pytest.mark.asyncio
async def test_finalize_rejects_an_already_finalized_resume() -> None:
    harness = _Harness()
    resume = await harness.seed_resume(status=ResumeStatus.FINALIZED, job_application_id=None)

    with pytest.raises(Conflict):
        await harness.service.finalize(_USER, resume.id, _HUMAN)


@pytest.mark.asyncio
async def test_finalize_rejects_a_dangling_reference() -> None:
    harness = _Harness()  # no bullet text seeded: the reference cannot resolve
    resume = await harness.seed_resume()

    with pytest.raises(Validation):
        await harness.service.finalize(_USER, resume.id, _HUMAN)


@pytest.mark.asyncio
async def test_finalize_snapshots_the_default_identity_when_no_variant_is_set() -> None:
    harness = _Harness()
    harness.bullets.own_bullet(_USER_PK, _BULLET_ID, "Shipped the pipeline.")
    harness.identity.set_default(_USER_PK, build_snapshot(full_name="Ada Lovelace"))
    resume = await harness.seed_resume(document=_draft_document(variant_id=None))

    await harness.service.finalize(_USER, resume.id, _HUMAN)

    document = ResumeDocument.model_validate(resume.document)
    assert document.header.identity_snapshot is not None
    assert document.header.identity_snapshot.full_name == "Ada Lovelace"


@pytest.mark.asyncio
async def test_finalize_preserves_a_preset_header_snapshot() -> None:
    harness = _Harness()
    harness.bullets.own_bullet(_USER_PK, _BULLET_ID, "Shipped the pipeline.")
    preset = _draft_document(variant_id=None).model_copy(
        update={
            "header": ResumeHeader(identity_snapshot=build_snapshot(full_name="Katherine Johnson"))
        }
    )
    resume = await harness.seed_resume(document=preset)

    await harness.service.finalize(_USER, resume.id, _HUMAN)

    document = ResumeDocument.model_validate(resume.document)
    assert document.header.identity_snapshot is not None
    assert document.header.identity_snapshot.full_name == "Katherine Johnson"
