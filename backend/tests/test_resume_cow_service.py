"""Sociable tests for the copy-on-write and promote paths of :class:`ResumeService`.

The real service runs over the in-memory resume repository, the real
:class:`LibraryCanonicalBulletWriter` over a shared in-memory library repository, a
bullet-text resolver reading that same library repository (so a written bullet
resolves in a snapshot exactly as against Postgres), and the real write-event seam
with a capturing consumer. Each test asserts the observable outcome: the canonical
bullet, the resume document, the write-derived ``resume_bullet_ref`` index, and the
published events (including the re-embed trigger on promote).
"""

from __future__ import annotations

from typing import Any

import pytest

from floresu.core.actor import Actor, ActorType
from floresu.core.errors import Conflict, NotFound, Validation
from floresu.core.events import REEMBED_CONTENT_HASH_KEY, SCOPE_METADATA_KEY, Action, WriteEvent
from floresu.library.hashing import compute_content_hash
from floresu.library.models import Bulletpoint
from floresu.resumes.cow import EditChannel, ResumeEditScope
from floresu.resumes.document import LibraryRefItem, LocalItem
from floresu.resumes.models import ResumeStatus
from floresu.resumes.schemas import (
    EditedEverywhereResult,
    ForkedThisResumeResult,
    ScopeEditRequest,
    ScopePromptResult,
)
from floresu.resumes.service import ResumeService
from tests.library_fakes import InMemoryLibraryRepository
from tests.resumes_fakes import (
    FakeSession,
    InMemoryResumeRepository,
    LibraryRepoTextResolver,
    build_bullet_writer,
    build_create_request,
    build_update,
    capturing_publisher,
)

_USER = "1"
_PK = 1
_HUMAN = Actor(type=ActorType.HUMAN)


class _Bench:
    def __init__(self) -> None:
        self.resume_repo = InMemoryResumeRepository()
        self.library_repo = InMemoryLibraryRepository()
        self.session = FakeSession()
        self.publisher, self.captured = capturing_publisher()
        self.service = ResumeService(
            self.session,  # type: ignore[arg-type]
            self.resume_repo,
            LibraryRepoTextResolver(self.library_repo),
            self.publisher,
            build_bullet_writer(self.session, self.publisher, library_repo=self.library_repo),  # type: ignore[arg-type]
        )

    async def seed_bullet(self, text: str) -> int:
        bullet = Bulletpoint(user_id=_PK, text=text, content_hash=compute_content_hash(text))
        await self.library_repo.add(bullet)
        return bullet.id

    async def stored_bullet(self, bullet_id: int) -> Bulletpoint:
        bullet = await self.library_repo.get(_PK, bullet_id)
        assert bullet is not None
        return bullet

    async def resume_referencing(self, bullet_id: int, *, item_id: str = "a") -> int:
        """Create a living resume whose one item references ``bullet_id``."""
        record = await self.service.create(_USER, _HUMAN, build_create_request())
        section: dict[str, Any] = {
            "id": "sec-work",
            "kind": "work",
            "title": "Experience",
            "item_order": [item_id],
            "items": {item_id: {"id": item_id, "kind": "library_ref", "bullet_id": bullet_id}},
        }
        await self.service.update(
            _USER, record.id, _HUMAN, record.revision, build_update(sections=[section])
        )
        return record.id

    async def resume_with_local_item(
        self, *, text: str, item_id: str = "a", source_refs: dict[str, Any] | None = None
    ) -> int:
        record = await self.service.create(_USER, _HUMAN, build_create_request())
        local: dict[str, Any] = {"id": item_id, "kind": "local", "text": text}
        if source_refs is not None:
            local["source_refs"] = source_refs
        section: dict[str, Any] = {
            "id": "sec-work",
            "kind": "work",
            "title": "Experience",
            "item_order": [item_id],
            "items": {item_id: local},
        }
        await self.service.update(
            _USER, record.id, _HUMAN, record.revision, build_update(sections=[section])
        )
        return record.id


def _events(captured: list[WriteEvent], entity_type: str, action: Action) -> list[WriteEvent]:
    return [e for e in captured if e.entity_type == entity_type and e.action is action]


def _meta(event: WriteEvent) -> dict[str, Any]:
    assert event.metadata is not None
    return event.metadata


# --- scope resolution: prompt / everywhere / this_resume ---


async def test_web_shared_bullet_returns_a_prompt_without_mutating() -> None:
    bench = _Bench()
    bullet_id = await bench.seed_bullet("Cut latency 40%.")
    await bench.resume_referencing(bullet_id, item_id="a")
    await bench.resume_referencing(bullet_id, item_id="b")
    before = len(bench.captured)

    result = await bench.service.bullet_update(
        _USER,
        _HUMAN,
        EditChannel.WEB,
        ScopeEditRequest(bullet_id=bullet_id, new_text="Cut latency 50%."),
    )

    assert isinstance(result, ScopePromptResult)
    assert result.used_in_count == 2
    assert result.bullet_id == bullet_id
    # Nothing was written: the canonical bullet is unchanged and no event fired.
    assert (await bench.stored_bullet(bullet_id)).text == "Cut latency 40%."
    assert len(bench.captured) == before


async def test_web_unshared_bullet_edits_everywhere_without_a_prompt() -> None:
    bench = _Bench()
    bullet_id = await bench.seed_bullet("Cut latency 40%.")
    resume_id = await bench.resume_referencing(bullet_id)

    result = await bench.service.bullet_update(
        _USER,
        _HUMAN,
        EditChannel.WEB,
        ScopeEditRequest(
            bullet_id=bullet_id, new_text="Cut latency 60%.", if_match_bullet_revision=1
        ),
    )

    assert isinstance(result, EditedEverywhereResult)
    assert result.bullet.text == "Cut latency 60%."
    assert result.bullet.revision == 2
    assert result.bullet.used_in_count == 1
    # The canonical bullet changed; the resume keeps its reference (resolves on read).
    assert (await bench.stored_bullet(bullet_id)).text == "Cut latency 60%."
    stored_resume = await bench.resume_repo.get(_PK, resume_id)
    assert stored_resume is not None
    assert stored_resume.document["sections"][0]["items"]["a"]["kind"] == "library_ref"

    edit_event = _events(bench.captured, "bullet", Action.UPDATE)[-1]
    assert _meta(edit_event)[SCOPE_METADATA_KEY] == "everywhere"
    assert _meta(edit_event)[REEMBED_CONTENT_HASH_KEY] == compute_content_hash("Cut latency 60%.")


async def test_this_resume_forks_a_local_copy_and_leaves_the_canonical_bullet() -> None:
    bench = _Bench()
    bullet_id = await bench.seed_bullet("Shared framing.")
    resume_a = await bench.resume_referencing(bullet_id)
    resume_b = await bench.resume_referencing(bullet_id)
    resume = await bench.resume_repo.get(_PK, resume_a)
    assert resume is not None

    result = await bench.service.bullet_update(
        _USER,
        _HUMAN,
        EditChannel.WEB,
        ScopeEditRequest(
            bullet_id=bullet_id,
            new_text="Forked framing.",
            scope=ResumeEditScope.THIS_RESUME,
            resume_id=resume_a,
            if_match_resume_revision=resume.revision,
        ),
    )

    assert isinstance(result, ForkedThisResumeResult)
    item = result.resume.document.sections[0].items["a"]
    assert isinstance(item, LocalItem)
    assert item.text == "Forked framing."
    assert item.forked_from_bullet_id == bullet_id
    # The canonical bullet is untouched, so resume B still resolves the shared text.
    assert (await bench.stored_bullet(bullet_id)).text == "Shared framing."
    # This resume no longer references the bullet; the other still does.
    assert bench.resume_repo.bullet_refs(resume_a) == []
    assert bench.resume_repo.bullet_refs(resume_b) == [bullet_id]

    fork_event = _events(bench.captured, "resume", Action.UPDATE)[-1]
    assert fork_event.entity_id == resume_a
    assert _meta(fork_event)[SCOPE_METADATA_KEY] == "this_resume"


async def test_this_resume_drops_the_ref_only_when_no_item_still_references_the_bullet() -> None:
    bench = _Bench()
    bullet_id = await bench.seed_bullet("Shared framing.")
    record = await bench.service.create(_USER, _HUMAN, build_create_request())
    section: dict[str, Any] = {
        "id": "sec-work",
        "kind": "work",
        "title": "Experience",
        "item_order": ["a", "b"],
        "items": {
            "a": {"id": "a", "kind": "library_ref", "bullet_id": bullet_id},
            "b": {"id": "b", "kind": "library_ref", "bullet_id": bullet_id},
        },
    }
    await bench.service.update(
        _USER, record.id, _HUMAN, record.revision, build_update(sections=[section])
    )
    resume = await bench.resume_repo.get(_PK, record.id)
    assert resume is not None

    # Forking replaces both references (both items in this resume become local forks),
    # so the bullet is no longer referenced here and the index row drops.
    await bench.service.bullet_update(
        _USER,
        _HUMAN,
        EditChannel.WEB,
        ScopeEditRequest(
            bullet_id=bullet_id,
            new_text="Forked framing.",
            scope=ResumeEditScope.THIS_RESUME,
            resume_id=record.id,
            if_match_resume_revision=resume.revision,
        ),
    )

    assert bench.resume_repo.bullet_refs(record.id) == []
    stored = await bench.resume_repo.get(_PK, record.id)
    assert stored is not None
    assert stored.document["sections"][0]["items"]["a"]["kind"] == "local"
    assert stored.document["sections"][0]["items"]["b"]["kind"] == "local"


# --- explicit-scope contract ---


async def test_mcp_edit_without_scope_is_a_validation_error() -> None:
    bench = _Bench()
    bullet_id = await bench.seed_bullet("Framing.")
    await bench.resume_referencing(bullet_id)

    with pytest.raises(Validation) as excinfo:
        await bench.service.bullet_update(
            _USER,
            _HUMAN,
            EditChannel.MCP,
            ScopeEditRequest(bullet_id=bullet_id, new_text="New framing."),
        )
    assert "scope" in (excinfo.value.fields or {})


async def test_mcp_edit_with_explicit_everywhere_applies() -> None:
    bench = _Bench()
    bullet_id = await bench.seed_bullet("Framing.")
    await bench.resume_referencing(bullet_id)

    result = await bench.service.bullet_update(
        _USER,
        _HUMAN,
        EditChannel.MCP,
        ScopeEditRequest(
            bullet_id=bullet_id,
            new_text="Agent framing.",
            scope=ResumeEditScope.EVERYWHERE,
            if_match_bullet_revision=1,
        ),
    )

    assert isinstance(result, EditedEverywhereResult)
    assert (await bench.stored_bullet(bullet_id)).text == "Agent framing."


# --- guard-token requirements and staleness ---


async def test_everywhere_without_the_bullet_revision_is_rejected() -> None:
    bench = _Bench()
    bullet_id = await bench.seed_bullet("Framing.")
    await bench.resume_referencing(bullet_id)

    with pytest.raises(Validation) as excinfo:
        await bench.service.bullet_update(
            _USER,
            _HUMAN,
            EditChannel.MCP,
            ScopeEditRequest(bullet_id=bullet_id, new_text="x", scope=ResumeEditScope.EVERYWHERE),
        )
    assert "if_match_bullet_revision" in (excinfo.value.fields or {})


async def test_everywhere_with_a_stale_bullet_revision_is_a_conflict() -> None:
    bench = _Bench()
    bullet_id = await bench.seed_bullet("Framing.")
    await bench.resume_referencing(bullet_id)

    with pytest.raises(Conflict):
        await bench.service.bullet_update(
            _USER,
            _HUMAN,
            EditChannel.MCP,
            ScopeEditRequest(
                bullet_id=bullet_id,
                new_text="x",
                scope=ResumeEditScope.EVERYWHERE,
                if_match_bullet_revision=99,
            ),
        )


async def test_this_resume_without_the_resume_id_is_rejected() -> None:
    bench = _Bench()
    bullet_id = await bench.seed_bullet("Framing.")
    await bench.resume_referencing(bullet_id)

    with pytest.raises(Validation) as excinfo:
        await bench.service.bullet_update(
            _USER,
            _HUMAN,
            EditChannel.MCP,
            ScopeEditRequest(
                bullet_id=bullet_id,
                new_text="x",
                scope=ResumeEditScope.THIS_RESUME,
                if_match_resume_revision=1,
            ),
        )
    assert "resume_id" in (excinfo.value.fields or {})


async def test_this_resume_without_the_resume_revision_is_rejected() -> None:
    bench = _Bench()
    bullet_id = await bench.seed_bullet("Framing.")
    resume_id = await bench.resume_referencing(bullet_id)

    with pytest.raises(Validation) as excinfo:
        await bench.service.bullet_update(
            _USER,
            _HUMAN,
            EditChannel.MCP,
            ScopeEditRequest(
                bullet_id=bullet_id,
                new_text="x",
                scope=ResumeEditScope.THIS_RESUME,
                resume_id=resume_id,
            ),
        )
    assert "if_match_resume_revision" in (excinfo.value.fields or {})


async def test_this_resume_with_a_stale_resume_revision_is_a_conflict() -> None:
    bench = _Bench()
    bullet_id = await bench.seed_bullet("Framing.")
    resume_id = await bench.resume_referencing(bullet_id)

    with pytest.raises(Conflict):
        await bench.service.bullet_update(
            _USER,
            _HUMAN,
            EditChannel.MCP,
            ScopeEditRequest(
                bullet_id=bullet_id,
                new_text="x",
                scope=ResumeEditScope.THIS_RESUME,
                resume_id=resume_id,
                if_match_resume_revision=99,
            ),
        )


async def test_this_resume_edit_of_an_unreferenced_bullet_is_rejected() -> None:
    bench = _Bench()
    bullet_id = await bench.seed_bullet("Framing.")
    # A resume that does NOT reference the bullet: there is nothing to fork.
    record = await bench.service.create(_USER, _HUMAN, build_create_request())

    with pytest.raises(Validation) as excinfo:
        await bench.service.bullet_update(
            _USER,
            _HUMAN,
            EditChannel.MCP,
            ScopeEditRequest(
                bullet_id=bullet_id,
                new_text="x",
                scope=ResumeEditScope.THIS_RESUME,
                resume_id=record.id,
                if_match_resume_revision=record.revision,
            ),
        )
    assert "bullet_id" in (excinfo.value.fields or {})


# --- promote ---


async def test_promote_creates_a_canonical_bullet_and_swaps_the_item() -> None:
    bench = _Bench()
    bench.library_repo.own_source(_PK, 7)
    bench.library_repo.own_worklog(_PK, 8)
    resume_id = await bench.resume_with_local_item(
        text="Net-new inline framing.",
        source_refs={"source_ids": [7], "worklog_ids": [8]},
    )
    resume = await bench.resume_repo.get(_PK, resume_id)
    assert resume is not None

    record = await bench.service.promote(_USER, resume_id, _HUMAN, resume.revision, "a")

    item = record.document.sections[0].items["a"]
    assert isinstance(item, LibraryRefItem)
    new_bullet_id = item.bullet_id
    # The promoted bullet carries the fork's text and provenance and enters the corpus.
    stored = await bench.stored_bullet(new_bullet_id)
    assert stored.text == "Net-new inline framing."
    assert (await bench.library_repo.source_ids_by_bullet([new_bullet_id]))[new_bullet_id] == [7]
    assert (await bench.library_repo.worklog_ids_by_bullet([new_bullet_id]))[new_bullet_id] == [8]
    # The write-derived index now references the new canonical bullet.
    assert bench.resume_repo.bullet_refs(resume_id) == [new_bullet_id]

    # Two writes: the bullet create (drives embedding) and the resume promote.
    create_event = _events(bench.captured, "bullet", Action.CREATE)[-1]
    assert _meta(create_event)[REEMBED_CONTENT_HASH_KEY] == compute_content_hash(
        "Net-new inline framing."
    )
    promote_event = _events(bench.captured, "resume", Action.PROMOTE)[-1]
    assert promote_event.entity_id == resume_id
    assert _meta(promote_event)["bullet_id"] == new_bullet_id
    assert _meta(promote_event)["item_id"] == "a"


async def test_promote_a_fork_carries_its_provenance() -> None:
    bench = _Bench()
    resume_id = await bench.resume_with_local_item(text="Forked text.")
    resume = await bench.resume_repo.get(_PK, resume_id)
    assert resume is not None

    record = await bench.service.promote(_USER, resume_id, _HUMAN, resume.revision, "a")
    item = record.document.sections[0].items["a"]
    assert isinstance(item, LibraryRefItem)
    assert (await bench.stored_bullet(item.bullet_id)).text == "Forked text."


async def test_promote_a_library_ref_item_is_rejected() -> None:
    bench = _Bench()
    bullet_id = await bench.seed_bullet("Framing.")
    resume_id = await bench.resume_referencing(bullet_id)
    resume = await bench.resume_repo.get(_PK, resume_id)
    assert resume is not None

    with pytest.raises(Validation) as excinfo:
        await bench.service.promote(_USER, resume_id, _HUMAN, resume.revision, "a")
    assert "item_id" in (excinfo.value.fields or {})


async def test_promote_an_unknown_item_is_not_found() -> None:
    bench = _Bench()
    resume_id = await bench.resume_with_local_item(text="Text.")
    resume = await bench.resume_repo.get(_PK, resume_id)
    assert resume is not None

    with pytest.raises(NotFound):
        await bench.service.promote(_USER, resume_id, _HUMAN, resume.revision, "missing")


async def test_promote_with_a_stale_revision_is_a_conflict() -> None:
    bench = _Bench()
    resume_id = await bench.resume_with_local_item(text="Text.")

    with pytest.raises(Conflict):
        await bench.service.promote(_USER, resume_id, _HUMAN, 99, "a")


async def test_promote_on_a_finalized_resume_is_rejected() -> None:
    bench = _Bench()
    resume_id = await bench.resume_with_local_item(text="Text.")
    resume = await bench.resume_repo.get(_PK, resume_id)
    assert resume is not None
    resume.status = ResumeStatus.FINALIZED

    with pytest.raises(Conflict):
        await bench.service.promote(_USER, resume_id, _HUMAN, resume.revision, "a")
