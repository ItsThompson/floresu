"""Unit tests for the embed gate and the EmbeddingService orchestration.

The gate (:func:`decide`) is pure, so it is tested directly across every branch.
The service runs over in-memory doubles (repository, corpus, provider) and a fake
session so the transaction boundary and the embed/store/purge flows are exercised
without Postgres or OpenAI.
"""

from __future__ import annotations

import pytest

from floresu.core.errors import Unauthorized
from floresu.embedding.config import EmbedItemKind
from floresu.embedding.models import Embedding
from floresu.embedding.schemas import EmbedOutcome
from floresu.embedding.service import EmbeddingService, decide
from tests.embedding_fakes import (
    FakeCorpusResolver,
    FakeEmbeddingProvider,
    InMemoryEmbeddingRepository,
    corpus_item,
)
from tests.support.fakes import FakeSession

_WORKLOG = EmbedItemKind.WORKLOG


def _existing(content_hash: str) -> Embedding:
    return Embedding(
        item_kind=_WORKLOG,
        item_id=1,
        user_id=1,
        content_hash=content_hash,
        vector=[0.0],
        model="m",
    )


def test_gate_missing_item_is_missing() -> None:
    assert decide(None, None, "h1") is EmbedOutcome.SKIPPED_MISSING


def test_gate_archived_item_is_archived() -> None:
    item = corpus_item("t", "h1", archived=True)
    assert decide(item, None, "h1") is EmbedOutcome.SKIPPED_ARCHIVED


def test_gate_hash_moved_past_the_job_is_superseded() -> None:
    item = corpus_item("t", "h2")
    assert decide(item, None, "h1") is EmbedOutcome.SKIPPED_SUPERSEDED


def test_gate_existing_vector_with_current_hash_is_idempotent() -> None:
    item = corpus_item("t", "h1")
    assert decide(item, _existing("h1"), "h1") is EmbedOutcome.SKIPPED_IDEMPOTENT


def test_gate_no_expected_hash_still_gates_idempotency() -> None:
    item = corpus_item("t", "h1")
    assert decide(item, _existing("h1"), None) is EmbedOutcome.SKIPPED_IDEMPOTENT
    assert decide(item, _existing("old"), None) is EmbedOutcome.APPLIED


def test_gate_fresh_content_applies() -> None:
    item = corpus_item("t", "h1")
    assert decide(item, None, "h1") is EmbedOutcome.APPLIED
    assert decide(item, _existing("old"), "h1") is EmbedOutcome.APPLIED


def _service() -> tuple[
    EmbeddingService, InMemoryEmbeddingRepository, FakeCorpusResolver, FakeEmbeddingProvider
]:
    session = FakeSession()
    repo = InMemoryEmbeddingRepository()
    resolver = FakeCorpusResolver()
    provider = FakeEmbeddingProvider()
    service = EmbeddingService(session, repo, resolver, provider)  # type: ignore[arg-type]
    return service, repo, resolver, provider


async def test_embed_item_applies_embeds_and_stores() -> None:
    service, repo, resolver, provider = _service()
    resolver.seed(_WORKLOG, 1, corpus_item("shipped the auth boundary", "h1"))

    outcome = await service.embed_item("1", _WORKLOG, 1, "h1")

    assert outcome is EmbedOutcome.APPLIED
    assert provider.calls == [["shipped the auth boundary"]]
    stored = await repo.get(_WORKLOG, 1)
    assert stored is not None
    assert stored.user_id == 1  # the string identity was cast to the bigint pk
    assert stored.content_hash == "h1"
    assert stored.model == provider.model
    # The fake encodes the text length in the first cell.
    assert stored.vector[0] == float(len("shipped the auth boundary"))


async def test_embed_item_idempotent_skips_the_provider_call() -> None:
    service, repo, resolver, provider = _service()
    resolver.seed(_WORKLOG, 1, corpus_item("text", "h1"))
    await repo.upsert(
        user_id=1, kind=_WORKLOG, item_id=1, content_hash="h1", vector=[1.0], model="m"
    )

    outcome = await service.embed_item("1", _WORKLOG, 1, "h1")

    assert outcome is EmbedOutcome.SKIPPED_IDEMPOTENT
    assert provider.calls == []  # no embed call for an already-current vector


async def test_embed_item_superseded_does_not_embed() -> None:
    service, _repo, resolver, provider = _service()
    resolver.seed(_WORKLOG, 1, corpus_item("text", "h2"))

    outcome = await service.embed_item("1", _WORKLOG, 1, "h1")

    assert outcome is EmbedOutcome.SKIPPED_SUPERSEDED
    assert provider.calls == []


async def test_embed_item_archived_removes_the_vector() -> None:
    service, repo, resolver, provider = _service()
    await repo.upsert(
        user_id=1, kind=_WORKLOG, item_id=1, content_hash="h1", vector=[1.0], model="m"
    )
    resolver.seed(_WORKLOG, 1, corpus_item("text", "h1", archived=True))

    outcome = await service.embed_item("1", _WORKLOG, 1, "h1")

    assert outcome is EmbedOutcome.SKIPPED_ARCHIVED
    assert await repo.get(_WORKLOG, 1) is None
    assert provider.calls == []


async def test_embed_item_missing_removes_any_vector() -> None:
    service, repo, _resolver, _provider = _service()
    await repo.upsert(
        user_id=1, kind=_WORKLOG, item_id=1, content_hash="h1", vector=[1.0], model="m"
    )
    # resolver has nothing seeded -> item is gone

    outcome = await service.embed_item("1", _WORKLOG, 1, "h1")

    assert outcome is EmbedOutcome.SKIPPED_MISSING
    assert await repo.get(_WORKLOG, 1) is None


async def test_store_vector_applies_without_calling_the_provider() -> None:
    service, repo, resolver, provider = _service()
    resolver.seed(_WORKLOG, 1, corpus_item("text", "h1"))

    outcome = await service.store_vector("1", _WORKLOG, 1, "h1", [0.5], "worker-model")

    assert outcome is EmbedOutcome.APPLIED
    assert provider.calls == []  # the worker already embedded; store never embeds
    stored = await repo.get(_WORKLOG, 1)
    assert stored is not None
    assert stored.vector == [0.5]
    assert stored.model == "worker-model"


async def test_store_vector_superseded_when_item_hash_moved() -> None:
    service, repo, resolver, _provider = _service()
    resolver.seed(_WORKLOG, 1, corpus_item("text", "h2"))

    outcome = await service.store_vector("1", _WORKLOG, 1, "h1", [0.5], "worker-model")

    assert outcome is EmbedOutcome.SKIPPED_SUPERSEDED
    assert await repo.get(_WORKLOG, 1) is None


async def test_delete_vector_removes_the_row() -> None:
    service, repo, _resolver, _provider = _service()
    await repo.upsert(
        user_id=1, kind=_WORKLOG, item_id=1, content_hash="h1", vector=[1.0], model="m"
    )

    await service.delete_vector("1", _WORKLOG, 1)

    assert await repo.get(_WORKLOG, 1) is None


async def test_resolve_item_returns_the_corpus_content() -> None:
    service, _repo, resolver, _provider = _service()
    resolver.seed(_WORKLOG, 7, corpus_item("the text", "h9"))

    item = await service.resolve_item("1", _WORKLOG, 7)

    assert item is not None
    assert item.text == "the text"
    assert item.content_hash == "h9"


async def test_embed_item_commits_the_transaction_on_apply() -> None:
    session = FakeSession()
    resolver = FakeCorpusResolver()
    resolver.seed(_WORKLOG, 1, corpus_item("text", "h1"))
    service = EmbeddingService(
        session,  # type: ignore[arg-type]
        InMemoryEmbeddingRepository(),
        resolver,
        FakeEmbeddingProvider(),
    )

    await service.embed_item("1", _WORKLOG, 1, "h1")

    assert session.commits == 1
    assert session.rollbacks == 0


@pytest.mark.parametrize("kind", list(EmbedItemKind))
async def test_embed_item_works_for_every_corpus_kind(kind: EmbedItemKind) -> None:
    service, repo, resolver, _provider = _service()
    resolver.seed(kind, 3, corpus_item("text", "h1"))

    outcome = await service.embed_item("1", kind, 3, "h1")

    assert outcome is EmbedOutcome.APPLIED
    assert await repo.get(kind, 3) is not None


async def test_embed_item_rejects_a_malformed_identity() -> None:
    service, _repo, resolver, provider = _service()
    resolver.seed(_WORKLOG, 1, corpus_item("text", "h1"))

    with pytest.raises(Unauthorized):
        await service.embed_item("not-a-pk", _WORKLOG, 1, "h1")

    assert provider.calls == []  # rejected at the boundary, before any embed call


async def test_store_vector_rejects_a_malformed_identity() -> None:
    service, repo, resolver, _provider = _service()
    resolver.seed(_WORKLOG, 1, corpus_item("text", "h1"))
    await repo.upsert(
        user_id=1, kind=_WORKLOG, item_id=1, content_hash="old", vector=[1.0], model="orig"
    )

    with pytest.raises(Unauthorized):
        await service.store_vector("not-a-pk", _WORKLOG, 1, "h1", [0.5], "worker-model")

    stored = await repo.get(_WORKLOG, 1)
    assert stored is not None
    assert stored.model == "orig"  # rejected before any upsert; the stored row is untouched


async def test_delete_vector_rejects_a_malformed_identity() -> None:
    service, repo, _resolver, _provider = _service()
    await repo.upsert(
        user_id=1, kind=_WORKLOG, item_id=1, content_hash="h1", vector=[1.0], model="m"
    )

    with pytest.raises(Unauthorized):
        await service.delete_vector("not-a-pk", _WORKLOG, 1)

    assert await repo.get(_WORKLOG, 1) is not None  # nothing purged for a bad id


async def test_resolve_item_rejects_a_malformed_identity() -> None:
    service, _repo, resolver, _provider = _service()
    resolver.seed(_WORKLOG, 7, corpus_item("the text", "h9"))

    with pytest.raises(Unauthorized):
        await service.resolve_item("not-a-pk", _WORKLOG, 7)
