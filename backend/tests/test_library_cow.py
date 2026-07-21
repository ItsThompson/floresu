"""Unit tests for :class:`LibraryCanonicalBulletWriter`: the library side of COW.

Sociable: the real writer runs over the in-memory library repository and the real
write-event seam with a capturing consumer, so each test asserts the observable
outcome (the mutated bullet, the returned record, and the published event) and, via
:func:`embed_intent`, that the event drives the embedding pipeline exactly like any
other bullet write. The writer is transaction-free (the resume service owns the
boundary), so the tests call it directly and inspect the captured events.
"""

from __future__ import annotations

from typing import Any

import pytest

from floresu.core.actor import Actor, ActorType
from floresu.core.errors import Conflict, NotFound, Validation
from floresu.core.events import REEMBED_CONTENT_HASH_KEY, SCOPE_METADATA_KEY, Action, WriteEvent
from floresu.embedding.config import EmbedItemKind
from floresu.embedding.enqueue import EmbedIntent, embed_intent
from floresu.library.cow import LibraryCanonicalBulletWriter
from floresu.library.hashing import compute_content_hash
from floresu.library.models import Bulletpoint
from tests.library_fakes import FakeSession, InMemoryLibraryRepository, capturing_publisher

_HUMAN = Actor(type=ActorType.HUMAN)
_USER = 1


def _meta(event: WriteEvent) -> dict[str, Any]:
    assert event.metadata is not None
    return event.metadata


async def _seed_bullet(repo: InMemoryLibraryRepository, *, text: str, user_id: int = _USER) -> int:
    bullet = Bulletpoint(user_id=user_id, text=text, content_hash=compute_content_hash(text))
    await repo.add(bullet)
    return bullet.id


def _writer(
    repo: InMemoryLibraryRepository,
) -> tuple[LibraryCanonicalBulletWriter, list[WriteEvent]]:
    publisher, captured = capturing_publisher()
    writer = LibraryCanonicalBulletWriter(FakeSession(), repo, publisher)  # type: ignore[arg-type]
    return writer, captured


async def test_edit_text_everywhere_overwrites_bumps_revision_and_reembeds() -> None:
    repo = InMemoryLibraryRepository()
    bullet_id = await _seed_bullet(repo, text="Original framing.")
    writer, captured = _writer(repo)

    record = await writer.edit_text_everywhere(
        _USER, _HUMAN, bullet_id, new_text="Sharper framing.", if_match_revision=1
    )

    assert record.text == "Sharper framing."
    assert record.revision == 2
    stored = await repo.get(_USER, bullet_id)
    assert stored is not None
    assert stored.text == "Sharper framing."
    assert stored.revision == 2
    assert stored.content_hash == compute_content_hash("Sharper framing.")

    event = captured[-1]
    assert event.entity_type == "bullet"
    assert event.entity_id == bullet_id
    assert event.action is Action.UPDATE
    assert _meta(event)[SCOPE_METADATA_KEY] == "everywhere"
    # The edit re-queues the bullet for embedding via the content-hash trigger.
    assert _meta(event)[REEMBED_CONTENT_HASH_KEY] == compute_content_hash("Sharper framing.")
    assert embed_intent(event) == EmbedIntent(
        user_id=_USER,
        kind=EmbedItemKind.BULLET,
        item_id=bullet_id,
        content_hash=compute_content_hash("Sharper framing."),
    )


async def test_edit_text_everywhere_rejects_a_stale_revision() -> None:
    repo = InMemoryLibraryRepository()
    bullet_id = await _seed_bullet(repo, text="Original framing.")
    writer, captured = _writer(repo)

    with pytest.raises(Conflict):
        await writer.edit_text_everywhere(
            _USER, _HUMAN, bullet_id, new_text="Stale.", if_match_revision=99
        )

    stored = await repo.get(_USER, bullet_id)
    assert stored is not None
    assert stored.text == "Original framing."
    assert stored.revision == 1
    assert captured == []


async def test_edit_text_everywhere_unknown_bullet_is_not_found() -> None:
    repo = InMemoryLibraryRepository()
    writer, _ = _writer(repo)

    with pytest.raises(NotFound):
        await writer.edit_text_everywhere(_USER, _HUMAN, 404, new_text="x", if_match_revision=1)


async def test_edit_text_everywhere_unchanged_text_bumps_revision_but_skips_reembed() -> None:
    repo = InMemoryLibraryRepository()
    bullet_id = await _seed_bullet(repo, text="Same framing.")
    writer, captured = _writer(repo)

    record = await writer.edit_text_everywhere(
        _USER, _HUMAN, bullet_id, new_text="Same framing.", if_match_revision=1
    )

    assert record.revision == 2
    event = captured[-1]
    # The content-hash gate: an unchanged text carries the scope but no re-embed key.
    assert _meta(event)[SCOPE_METADATA_KEY] == "everywhere"
    assert REEMBED_CONTENT_HASH_KEY not in _meta(event)
    assert embed_intent(event) is None


async def test_create_from_local_mints_a_canonical_bullet_and_enqueues_embedding() -> None:
    repo = InMemoryLibraryRepository()
    repo.own_source(_USER, 7)
    repo.own_worklog(_USER, 8)
    writer, captured = _writer(repo)

    bullet_id = await writer.create_from_local(
        _USER, _HUMAN, text="Promoted framing.", source_ids=[7], worklog_ids=[8]
    )

    stored = await repo.get(_USER, bullet_id)
    assert stored is not None
    assert stored.text == "Promoted framing."
    assert (await repo.source_ids_by_bullet([bullet_id]))[bullet_id] == [7]
    assert (await repo.worklog_ids_by_bullet([bullet_id]))[bullet_id] == [8]

    event = captured[-1]
    assert event.entity_type == "bullet"
    assert event.entity_id == bullet_id
    assert event.action is Action.CREATE
    assert embed_intent(event) == EmbedIntent(
        user_id=_USER,
        kind=EmbedItemKind.BULLET,
        item_id=bullet_id,
        content_hash=compute_content_hash("Promoted framing."),
    )


async def test_create_from_local_rejects_an_unowned_source() -> None:
    repo = InMemoryLibraryRepository()
    writer, captured = _writer(repo)

    with pytest.raises(Validation):
        await writer.create_from_local(_USER, _HUMAN, text="x", source_ids=[999], worklog_ids=[])
    assert captured == []


async def test_create_from_local_allows_a_bullet_with_no_edges() -> None:
    repo = InMemoryLibraryRepository()
    writer, captured = _writer(repo)

    bullet_id = await writer.create_from_local(
        _USER, _HUMAN, text="Net-new inline.", source_ids=[], worklog_ids=[]
    )

    assert (await repo.get(_USER, bullet_id)) is not None
    assert captured[-1].action is Action.CREATE
