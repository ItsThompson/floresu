"""SourceService: the single home for source lifecycle rules and transactions.

Every source write runs here and nowhere else, so the web and agent adapters stay
thin and provenance is uniform. Each mutate wraps its work in the ``transaction``
boundary and publishes exactly one :class:`WriteEvent` through the write-event
seam from *inside* that boundary, so the audit row (the seam's transactional
consumer) commits or rolls back atomically with the content write. The resolved
:class:`Actor` (human vs named agent) is carried into every event, so the audit
log and activity feed attribute the write.

Create writes the base ``sources`` row and its one kind-locked subtype row in a
single transaction. Edit overwrites the full representation (``kind`` is
immutable). Archive is soft (stamps ``archived_at``; restore clears it). Reorder
assigns ``sort_order`` by submitted position within one kind. Identity crosses the
boundary as a string and is cast to the bigint PK here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from floresu.core.db import transaction
from floresu.core.errors import Conflict, NotFound, Validation
from floresu.core.events import Action, emit_write_event
from floresu.core.identity import resolve_user_pk
from floresu.core.observability import track_failures
from floresu.profile.config import DEFAULT_LIST_LIMIT, ENTITY_TYPE
from floresu.profile.injection import Clock, utcnow
from floresu.profile.models import SUBTYPE_MODELS, Source, SourceKind
from floresu.profile.schemas import (
    SourceRecord,
    SourceSummary,
    subtype_values,
    to_record,
    to_summary,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.core.actor import Actor
    from floresu.core.events import WriteEventPublisher
    from floresu.profile.repository import SourceRepository
    from floresu.profile.schemas import ReorderRequest, SourceWrite


@track_failures("profile")
class SourceService:
    """Business rules for the ground-truth sources layer."""

    def __init__(
        self,
        session: AsyncSession,
        repo: SourceRepository,
        publisher: WriteEventPublisher,
        *,
        clock: Clock = utcnow,
    ) -> None:
        # The session backs both the ``transaction`` boundary and the event
        # publish (the audit consumer enlists in it); the repository is built over
        # the same session so its writes join that transaction.
        self._session = session
        self._repo = repo
        self._publisher = publisher
        # Injected so archive/restore timestamps are assertable under a pinned
        # clock; the default reproduces the ambient UTC call.
        self._clock = clock

    async def create(self, user_id: str, actor: Actor, write: SourceWrite) -> SourceRecord:
        """Create a source: one base row and one kind-locked subtype row atomically."""
        pk = resolve_user_pk(user_id)
        source = Source(
            user_id=pk,
            kind=write.kind,
            display_label=write.display_label,
            date_start=write.date_start,
            date_end=write.date_end,
            summary=write.summary,
        )
        subtype = SUBTYPE_MODELS[write.kind](kind=write.kind, **subtype_values(write))
        async with transaction(self._session):
            await self._repo.add(source, subtype)
            await self._publish(
                pk, actor, source.id, Action.CREATE, summary=_created_summary(write)
            )
        return to_record(source, subtype)

    async def get(self, user_id: str, source_id: int) -> SourceRecord:
        """Read one source with its typed subtype detail (joins one subtype table)."""
        pk = resolve_user_pk(user_id)
        found = await self._repo.get_detail(pk, source_id)
        if found is None:
            raise _not_found(source_id)
        source, subtype = found
        return to_record(source, subtype)

    async def list_sources(
        self,
        user_id: str,
        *,
        kind: SourceKind | None = None,
        include_archived: bool = False,
        limit: int = DEFAULT_LIST_LIMIT,
    ) -> list[SourceSummary]:
        """List sources (common columns only); active-only and per-kind by default."""
        pk = resolve_user_pk(user_id)
        rows = await self._repo.list(pk, kind=kind, include_archived=include_archived, limit=limit)
        return [to_summary(row) for row in rows]

    async def update(
        self, user_id: str, source_id: int, actor: Actor, write: SourceWrite
    ) -> SourceRecord:
        """Overwrite every editable field; ``kind`` is immutable. Records an update."""
        pk = resolve_user_pk(user_id)
        found = await self._repo.get_detail(pk, source_id)
        if found is None:
            raise _not_found(source_id)
        source, subtype = found
        if write.kind != source.kind:
            raise Validation(
                "A source's kind cannot be changed.",
                fields={"kind": f"Expected {source.kind.value}, got {write.kind.value}."},
            )
        async with transaction(self._session):
            source.display_label = write.display_label
            source.date_start = write.date_start
            source.date_end = write.date_end
            source.summary = write.summary
            for column, value in subtype_values(write).items():
                setattr(subtype, column, value)
            await self._publish(
                pk, actor, source.id, Action.UPDATE, summary=_edited_summary(source)
            )
        return to_record(source, subtype)

    async def archive(self, user_id: str, source_id: int, actor: Actor) -> SourceRecord:
        """Soft-archive: stamp ``archived_at`` so the source drops from active lists."""
        pk = resolve_user_pk(user_id)
        found = await self._repo.get_detail(pk, source_id)
        if found is None:
            raise _not_found(source_id)
        source, subtype = found
        if source.archived_at is not None:
            raise Conflict("This source is already archived.")
        async with transaction(self._session):
            source.archived_at = self._clock()
            await self._publish(
                pk, actor, source.id, Action.ARCHIVE, summary=_archived_summary(source)
            )
        return to_record(source, subtype)

    async def restore(self, user_id: str, source_id: int, actor: Actor) -> SourceRecord:
        """Clear ``archived_at`` so an archived source returns to active lists."""
        pk = resolve_user_pk(user_id)
        found = await self._repo.get_detail(pk, source_id)
        if found is None:
            raise _not_found(source_id)
        source, subtype = found
        if source.archived_at is None:
            raise Conflict("This source is not archived.")
        async with transaction(self._session):
            source.archived_at = None
            await self._publish(
                pk, actor, source.id, Action.RESTORE, summary=_restored_summary(source)
            )
        return to_record(source, subtype)

    async def reorder(
        self, user_id: str, actor: Actor, request: ReorderRequest
    ) -> list[SourceSummary]:
        """Persist ``sort_order`` by submitted position within one kind.

        The submit must be a permutation of the kind's full active section: every
        active source of that kind, listed exactly once. A partial submit is
        rejected, so ``sort_order`` can never end up duplicated or partially
        applied. Ordering is independent per kind because section lists filter by
        kind, so each kind carries its own 0-based positions.
        """
        pk = resolve_user_pk(user_id)
        ordered_ids = request.source_ids
        if len(set(ordered_ids)) != len(ordered_ids):
            raise Validation("The reorder contains duplicate source ids.")
        section = await self._repo.active_section(pk, request.kind)
        by_id = {row.id: row for row in section}
        if set(ordered_ids) != set(by_id):
            raise Validation(
                "A reorder must list every active source in the section exactly once.",
                fields={
                    "source_ids": (
                        f"Expected the {len(by_id)} active {request.kind.value} "
                        f"source(s); got {len(ordered_ids)}."
                    )
                },
            )
        async with transaction(self._session):
            for position, source_id in enumerate(ordered_ids):
                by_id[source_id].sort_order = position
            await self._publish(
                pk,
                actor,
                ordered_ids[0],
                Action.REORDER,
                summary=f"Reordered {len(ordered_ids)} {request.kind.value} sources",
                metadata={"kind": request.kind.value, "order": ordered_ids},
            )
        return [to_summary(by_id[source_id]) for source_id in ordered_ids]

    async def _publish(
        self,
        user_pk: int,
        actor: Actor,
        entity_id: int,
        action: Action,
        *,
        summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await emit_write_event(
            self._publisher,
            self._session,
            user_id=user_pk,
            actor=actor,
            entity_type=ENTITY_TYPE,
            entity_id=entity_id,
            action=action,
            summary=summary,
            metadata=metadata,
        )


def _not_found(source_id: int) -> NotFound:
    # 404-over-403: a source another account owns is scoped out of the read, so a
    # miss is indistinguishable from "does not exist" (no existence leak).
    return NotFound(f"No source with id {source_id}.")


def _created_summary(write: SourceWrite) -> str:
    return f"Added {write.kind.value} “{write.display_label}”"


def _edited_summary(source: Source) -> str:
    return f"Edited {source.kind.value} “{source.display_label}”"


def _archived_summary(source: Source) -> str:
    return f"Archived {source.kind.value} “{source.display_label}”"


def _restored_summary(source: Source) -> str:
    return f"Restored {source.kind.value} “{source.display_label}”"
