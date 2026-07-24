"""ResumeRenderService: resolve, render, and stream (preview) or persist (export).

Sociable tests: the real service and render module (over a fake Typst compiler) run
against in-memory doubles at the true boundaries (Postgres via the render repo and
resolvers, R2 via the fake store, the write-event seam via a capturing consumer). No
real Typst, R2, or database. They assert preview streams and never persists, export
persists at the revision key and records it and publishes one RENDER event, preview
renders the live document while export renders the frozen revision, identity falls
back to the default, and a render failure blocks export cleanly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
import structlog

from floresu.core.errors import NotFound
from floresu.core.events import Action
from floresu.rendering.errors import RenderError
from floresu.rendering.module import RenderModule
from floresu.resumes.document import (
    LibraryRefItem,
    LocalItem,
    ResumeDocument,
    ResumeHeader,
    ResumeSection,
    SectionKind,
)
from floresu.resumes.render_service import ResumeRenderService
from tests.rendering_fakes import (
    FakeTypstCompiler,
    InMemoryIdentityResolver,
    InMemoryRenderRepository,
    build_resolved_document,
    build_snapshot,
    local_section,
    resume_row,
    revision_row,
)
from tests.resumes_fakes import InMemoryBulletTextResolver
from tests.storage_fakes import FakeObjectStore
from tests.support.fakes import CapturingWriteEventPublisher, FakeSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.core.actor import Actor
    from floresu.core.events import WriteEvent
    from floresu.rendering.typst import TypstCompiler

from floresu.core.actor import Actor, ActorType

_HUMAN = Actor(type=ActorType.HUMAN)


class _Harness:
    def __init__(
        self,
        service: ResumeRenderService,
        repo: InMemoryRenderRepository,
        bullets: InMemoryBulletTextResolver,
        identity: InMemoryIdentityResolver,
        compiler: FakeTypstCompiler,
        store: FakeObjectStore,
        captured: list[WriteEvent],
    ) -> None:
        self.service = service
        self.repo = repo
        self.bullets = bullets
        self.identity = identity
        self.compiler = compiler
        self.store = store
        self.captured = captured

    def rendered_payload(self) -> dict[str, object]:
        return cast("dict[str, object]", json.loads(self.compiler.calls[-1][2]))


def _harness(*, compiler: TypstCompiler | None = None) -> _Harness:
    repo = InMemoryRenderRepository()
    bullets = InMemoryBulletTextResolver()
    identity = InMemoryIdentityResolver()
    fake_compiler = compiler if compiler is not None else FakeTypstCompiler()
    module = RenderModule(fake_compiler, templates_dir=Path("/tmpl"))
    store = FakeObjectStore()
    publisher = CapturingWriteEventPublisher()
    captured = publisher.captured
    service = ResumeRenderService(
        cast("AsyncSession", FakeSession()),
        repo,
        bullets,
        identity,
        module,
        store,
        publisher,
    )
    return _Harness(
        service,
        repo,
        bullets,
        identity,
        cast("FakeTypstCompiler", fake_compiler),
        store,
        captured,
    )


def _live_document() -> ResumeDocument:
    """A live draft document: a library_ref plus an inline item, header by variant id."""
    return ResumeDocument(
        schema_version=1,
        header=ResumeHeader(identity_variant_id=5),
        template_id="classic",
        sections=[
            ResumeSection(
                id="s",
                kind=SectionKind.WORK,
                title="Experience",
                item_order=["r", "l"],
                items={
                    "r": LibraryRefItem(id="r", bullet_id=100),
                    "l": LocalItem(id="l", text="inline line"),
                },
            )
        ],
    )


def _frozen_document(text: str) -> ResumeDocument:
    """A revision snapshot: all inline, header by variant id (no snapshot yet)."""
    return ResumeDocument(
        schema_version=1,
        header=ResumeHeader(identity_variant_id=5),
        template_id="classic",
        sections=[local_section("s", "work", "Experience", [text])],
    )


async def test_preview_streams_bytes_and_never_persists() -> None:
    h = _harness()
    h.repo.seed_resume(resume_row(resume_id=1, user_id=1, document=build_resolved_document()))

    pdf = await h.service.preview("1", 1)

    assert pdf == b"%PDF-1.7 fake"
    assert h.store.objects == {}  # preview is ephemeral: nothing written to R2
    assert h.captured == []  # and publishes no event


async def test_preview_resolves_references_and_identity_into_the_render() -> None:
    h = _harness()
    h.repo.seed_resume(resume_row(resume_id=1, user_id=1, document=_live_document()))
    h.bullets.own_bullet(1, 100, "resolved canonical text")
    h.identity.own_variant(1, 5, build_snapshot(full_name="Ada Lovelace"))

    await h.service.preview("1", 1)

    payload = h.rendered_payload()
    assert payload["full_name"] == "Ada Lovelace"
    section = cast("list[dict[str, object]]", payload["sections"])[0]
    assert section["items"] == ["resolved canonical text", "inline line"]


async def test_preview_honors_a_template_override() -> None:
    h = _harness()
    h.repo.seed_resume(resume_row(resume_id=1, user_id=1, document=build_resolved_document()))

    await h.service.preview("1", 1, template_id="does-not-exist")

    # Unknown id falls back to the P0 classic directory.
    assert h.compiler.calls[-1][1] == Path("/tmpl/classic")


async def test_preview_missing_resume_is_not_found() -> None:
    h = _harness()
    with pytest.raises(NotFound):
        await h.service.preview("1", 404)


async def test_a_render_failure_blocks_the_preview() -> None:
    h = _harness(compiler=_RaisingCompiler())
    h.repo.seed_resume(resume_row(resume_id=1, user_id=1, document=build_resolved_document()))

    with pytest.raises(RenderError):
        await h.service.preview("1", 1)


async def test_preview_blocks_when_a_referenced_bullet_no_longer_resolves() -> None:
    h = _harness()
    h.repo.seed_resume(resume_row(resume_id=1, user_id=1, document=_live_document()))
    h.identity.own_variant(1, 5, build_snapshot())
    # Bullet 100 is never seeded, so the live reference no longer resolves to text.
    with pytest.raises(RenderError):
        await h.service.preview("1", 1)


async def test_export_persists_at_the_revision_key_records_it_and_publishes_render() -> None:
    h = _harness()
    document = build_resolved_document()
    h.repo.seed_resume(resume_row(resume_id=7, user_id=1, document=document))
    h.repo.seed_revision(revision_row(resume_id=7, revision_no=3, document=document))

    result = await h.service.export("1", 7, _HUMAN)

    assert result.object_key == "u/1/r/7/rev/3.pdf"
    assert result.revision == 3
    assert result.download_url == "https://fake-r2.local/u/1/r/7/rev/3.pdf?signed=1"
    stored, content_type = h.store.objects["u/1/r/7/rev/3.pdf"]
    assert stored == b"%PDF-1.7 fake"
    assert content_type == "application/pdf"
    assert h.repo.pdf_keys[(7, 3)] == "u/1/r/7/rev/3.pdf"

    assert len(h.captured) == 1
    event = h.captured[0]
    assert event.action is Action.RENDER
    assert event.entity_type == "resume"
    assert event.entity_id == 7
    assert event.metadata == {"template": "classic", "revision": 3}


async def test_export_renders_the_frozen_revision_not_the_live_document() -> None:
    h = _harness()
    # The live document differs from the frozen revision; export must render the frozen one.
    h.repo.seed_resume(
        resume_row(
            resume_id=7,
            user_id=1,
            document=_frozen_document("LIVE edited-since-save text"),
        )
    )
    h.repo.seed_revision(
        revision_row(resume_id=7, revision_no=2, document=_frozen_document("FROZEN snapshot text"))
    )
    h.identity.set_default(1, build_snapshot(full_name="Grace Hopper"))

    await h.service.export("1", 7, _HUMAN)

    payload = h.rendered_payload()
    section = cast("list[dict[str, object]]", payload["sections"])[0]
    assert section["items"] == ["FROZEN snapshot text"]
    # Identity fell back to the user's default variant (the frozen header carries no snapshot).
    assert payload["full_name"] == "Grace Hopper"


async def test_export_without_a_revision_is_a_render_error() -> None:
    h = _harness()
    h.repo.seed_resume(resume_row(resume_id=7, user_id=1, document=build_resolved_document()))

    with pytest.raises(RenderError):
        await h.service.export("1", 7, _HUMAN)


async def test_export_without_a_revision_logs_a_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = _harness()
    h.repo.seed_resume(resume_row(resume_id=7, user_id=1, document=build_resolved_document()))
    cap = structlog.testing.CapturingLogger()
    monkeypatch.setattr("floresu.resumes.render_service._log", cap)
    with pytest.raises(RenderError):
        await h.service.export("1", 7, _HUMAN)
    warnings = [call for call in cap.calls if call.method_name == "warning"]
    assert len(warnings) == 1
    assert warnings[0].args == ("resume_export_no_revision",)
    assert warnings[0].kwargs == {"user_id": 1, "resume_id": 7}


async def test_a_missing_referenced_bullet_logs_a_render_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = _harness()
    h.repo.seed_resume(resume_row(resume_id=1, user_id=1, document=_live_document()))
    h.identity.own_variant(1, 5, build_snapshot())
    cap = structlog.testing.CapturingLogger()
    monkeypatch.setattr("floresu.resumes.render_service._log", cap)
    # Bullet 100 is never seeded, so the live reference no longer resolves to text.
    with pytest.raises(RenderError):
        await h.service.preview("1", 1)
    warnings = [call for call in cap.calls if call.method_name == "warning"]
    assert len(warnings) == 1
    assert warnings[0].args == ("resume_render_missing_bullets",)
    assert warnings[0].kwargs == {"user_id": 1, "missing": [100]}


async def test_a_render_failure_blocks_export_without_persisting_or_publishing() -> None:
    h = _harness(compiler=_RaisingCompiler())
    document = build_resolved_document()
    h.repo.seed_resume(resume_row(resume_id=7, user_id=1, document=document))
    h.repo.seed_revision(revision_row(resume_id=7, revision_no=1, document=document))

    with pytest.raises(RenderError):
        await h.service.export("1", 7, _HUMAN)

    assert h.store.objects == {}
    assert h.repo.pdf_keys == {}
    assert h.captured == []


async def test_export_missing_resume_is_not_found() -> None:
    h = _harness()
    with pytest.raises(NotFound):
        await h.service.export("1", 404, _HUMAN)


def test_list_templates_returns_the_registry() -> None:
    h = _harness()
    assert any(info.id == "classic" for info in h.service.list_templates())


class _RaisingCompiler:
    """A Typst compiler stand-in that always fails, to exercise the render-error path."""

    def compile(self, entrypoint: Path, root: Path, data_json: str) -> bytes:
        raise RenderError("This resume could not be rendered: boom")
