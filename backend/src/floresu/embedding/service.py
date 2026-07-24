"""EmbeddingService: the one home for the embed gate, store, and purge rules.

Two entry points share one gate:

- :meth:`embed_item` is the synchronous fast-path. It resolves the item, applies
  the gate, and (if the gate says apply) embeds the text inline via the injected
  provider and stores the vector, all in one transaction. It is the same routine
  the write-then-search agent turn runs before returning, so an immediate semantic
  search sees the vector.
- :meth:`store_vector` is the worker write-back. The worker embedded the text in
  its own process and posts the vector plus the hash it embedded at; this re-applies
  the gate against the item's *current* state (so a job the item has moved past is
  dropped, not applied) and stores it.

The gate (:func:`decide`) is pure and the single definition of the pipeline rules:
a missing or archived item has its vector removed and nothing written; a job whose
hash no longer matches the item is superseded; a vector already carrying the
current hash is an idempotent no-op; otherwise the vector is written. Each public
method owns its ``transaction`` boundary, so the read/gate/write is atomic; the
fast-path's inline provider call runs inside that boundary (bounded to one item,
acceptable at the P0 single-box scale).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.core.db import transaction
from floresu.core.identity import resolve_user_pk
from floresu.core.logging import get_logger
from floresu.core.observability import track_failures
from floresu.embedding.schemas import CorpusItem, EmbedOutcome

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.embedding.config import EmbedItemKind
    from floresu.embedding.corpus import CorpusResolver
    from floresu.embedding.models import Embedding
    from floresu.embedding.provider import EmbeddingProvider
    from floresu.embedding.repository import EmbeddingRepository

_log = get_logger("floresu-embedding")

# Gate outcomes where a requested embed did not apply (a degraded outcome), as
# opposed to the idempotent no-op and the applied write.
_GATE_DROPPED = frozenset(
    {
        EmbedOutcome.SKIPPED_MISSING,
        EmbedOutcome.SKIPPED_ARCHIVED,
        EmbedOutcome.SKIPPED_SUPERSEDED,
    }
)


def decide(
    item: CorpusItem | None, existing: Embedding | None, expected_hash: str | None
) -> EmbedOutcome:
    """Pure gate: decide what to do for one embed/store attempt.

    ``expected_hash`` is the job's enqueued hash, or ``None`` to embed the item's
    current content regardless (only the idempotency check then applies). Returns
    ``APPLIED`` to mean "write the vector"; the caller performs the write.
    """
    if item is None:
        return EmbedOutcome.SKIPPED_MISSING
    if item.archived:
        return EmbedOutcome.SKIPPED_ARCHIVED
    if expected_hash is not None and item.content_hash != expected_hash:
        return EmbedOutcome.SKIPPED_SUPERSEDED
    if existing is not None and existing.content_hash == item.content_hash:
        return EmbedOutcome.SKIPPED_IDEMPOTENT
    return EmbedOutcome.APPLIED


@track_failures("embedding")
class EmbeddingService:
    """Embed, store, and purge one corpus item's vector under the caller's session."""

    def __init__(
        self,
        session: AsyncSession,
        repo: EmbeddingRepository,
        resolver: CorpusResolver,
        provider: EmbeddingProvider,
    ) -> None:
        self._session = session
        self._repo = repo
        self._resolver = resolver
        self._provider = provider

    async def resolve_item(
        self, user_id: str, kind: EmbedItemKind, item_id: int
    ) -> CorpusItem | None:
        """Read the item's embeddable text + current hash + archive state."""
        pk = resolve_user_pk(user_id)
        return await self._resolver.resolve(self._session, pk, kind, item_id)

    async def embed_item(
        self, user_id: str, kind: EmbedItemKind, item_id: int, expected_hash: str | None
    ) -> EmbedOutcome:
        """Fast-path: resolve, gate, and (if applying) embed inline and store."""
        pk = resolve_user_pk(user_id)
        async with transaction(self._session):
            outcome, target = await self._gate(pk, kind, item_id, expected_hash)
            if outcome is not EmbedOutcome.APPLIED or target is None:
                return outcome
            vectors = await self._provider.embed([target.text])
            await self._repo.upsert(
                user_id=pk,
                kind=kind,
                item_id=item_id,
                content_hash=target.content_hash,
                vector=vectors[0],
                model=self._provider.model,
            )
            return EmbedOutcome.APPLIED

    async def store_vector(
        self,
        user_id: str,
        kind: EmbedItemKind,
        item_id: int,
        source_hash: str,
        vector: list[float],
        model: str,
    ) -> EmbedOutcome:
        """Worker write-back: re-gate against current state, then store if current."""
        pk = resolve_user_pk(user_id)
        async with transaction(self._session):
            outcome, target = await self._gate(pk, kind, item_id, source_hash)
            if outcome is not EmbedOutcome.APPLIED or target is None:
                return outcome
            await self._repo.upsert(
                user_id=pk,
                kind=kind,
                item_id=item_id,
                content_hash=target.content_hash,
                vector=vector,
                model=model,
            )
            return EmbedOutcome.APPLIED

    async def delete_vector(self, user_id: str, kind: EmbedItemKind, item_id: int) -> None:
        """Purge an item's vector (archive/delete); a no-op if it has none."""
        # Reject a malformed identity at the boundary so a bad id still yields 401;
        # the purge is keyed by (kind, item_id), not the caller, so the resolved pk
        # is not needed past this guard.
        resolve_user_pk(user_id)
        async with transaction(self._session):
            await self._repo.delete(kind, item_id)

    async def _gate(
        self, pk: int, kind: EmbedItemKind, item_id: int, expected_hash: str | None
    ) -> tuple[EmbedOutcome, CorpusItem | None]:
        """Resolve the item, apply the gate, and remove the vector on missing/archived.

        Returns the gate outcome plus the resolved item when the caller should
        write (``APPLIED``); on a skip outcome the item is ``None``. Runs inside the
        caller's open ``transaction`` so the stale-vector removal commits with it.
        """
        item = await self._resolver.resolve(self._session, pk, kind, item_id)
        existing = await self._repo.get(kind, item_id)
        outcome = decide(item, existing, expected_hash)
        if outcome in _GATE_DROPPED:
            _log.warning(
                "embedding_gate_dropped", kind=kind.value, item_id=item_id, outcome=outcome.value
            )
        if outcome in (EmbedOutcome.SKIPPED_MISSING, EmbedOutcome.SKIPPED_ARCHIVED):
            await self._repo.delete(kind, item_id)
            return outcome, None
        if outcome is EmbedOutcome.APPLIED:
            return outcome, item
        return outcome, None
