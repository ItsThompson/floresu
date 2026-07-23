"""WorklogService: the single home for worklog lifecycle rules and transactions.

Every worklog write runs here and nowhere else, so the web and agent adapters stay
thin and provenance is uniform. Each mutate wraps its work in the ``transaction``
boundary and publishes exactly one :class:`WriteEvent` through the write-event
seam from *inside* that boundary, so the audit row (the seam's transactional
consumer) commits or rolls back atomically with the content write. The resolved
:class:`Actor` (human vs named agent) is carried into every event.

Create requires a title and a date; description, tags, and source attachments are
optional (zero, one, or many sources). Edit overwrites the full representation:
setting the tag list adds a new label or drops an omitted one, and setting the
source list re-attaches. The content hash is recomputed on every edit and a
re-embed is signalled (the hash rides the event metadata) only when it changes.
Archive is soft (stamps ``archived_at``; restore clears it). A new tag label
creates a per-user tag; an existing label is reused; removing a tag from an entry
drops only the edge, never the tag row.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from floresu.core.db import transaction
from floresu.core.errors import Conflict, NotFound, Unauthorized, Validation
from floresu.core.events import REEMBED_CONTENT_HASH_KEY, Action, emit_write_event
from floresu.core.observability import track_failures
from floresu.worklog.config import DEFAULT_LIST_LIMIT, ENTITY_TYPE
from floresu.worklog.hashing import compute_content_hash
from floresu.worklog.injection import Clock, utcnow
from floresu.worklog.models import WorklogEntry
from floresu.worklog.normalize import dedupe, normalize_labels
from floresu.worklog.schemas import (
    TagRead,
    WorklogRecord,
    WorklogSummary,
    to_record,
    to_summary,
    to_tag_read,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.core.actor import Actor
    from floresu.core.events import WriteEventPublisher
    from floresu.worklog.repository import WorklogRepository
    from floresu.worklog.schemas import WorklogWrite


@track_failures("worklog")
class WorklogService:
    """Business rules for the worklog domain: entries, tags, and source attachment."""

    def __init__(
        self,
        session: AsyncSession,
        repo: WorklogRepository,
        publisher: WriteEventPublisher,
        *,
        clock: Clock = utcnow,
    ) -> None:
        self._session = session
        self._repo = repo
        self._publisher = publisher
        self._clock = clock

    async def create(self, user_id: str, actor: Actor, write: WorklogWrite) -> WorklogRecord:
        """Create an entry, attach its sources, and reconcile its tags atomically."""
        pk = _require_user_pk(user_id)
        source_ids = dedupe(write.source_ids)
        await self._require_owned_sources(pk, source_ids)
        labels = normalize_labels(write.tags)
        content_hash = compute_content_hash(write.title, write.description)
        entry = WorklogEntry(
            user_id=pk,
            title=write.title,
            entry_date=write.entry_date,
            description=write.description,
            content_hash=content_hash,
        )
        async with transaction(self._session):
            await self._repo.add(entry)
            await self._attach(entry.id, pk, labels, source_ids)
            # A create always warrants embedding: carry the hash so the embed
            # consumer picks it up (a no-op until that side channel is registered).
            await self._publish(
                pk,
                actor,
                entry.id,
                Action.CREATE,
                summary=_created_summary(write),
                metadata={REEMBED_CONTENT_HASH_KEY: content_hash},
            )
        return await self._record_after_write(entry, labels, source_ids)

    async def get(self, user_id: str, worklog_id: int) -> WorklogRecord:
        """Read one entry with its tags, attached sources, and framing bullets."""
        pk = _require_user_pk(user_id)
        entry = await self._repo.get(pk, worklog_id)
        if entry is None:
            raise _not_found(worklog_id)
        tags = (await self._repo.tag_labels_by_worklog([worklog_id])).get(worklog_id, [])
        source_ids = (await self._repo.source_ids_by_worklog([worklog_id])).get(worklog_id, [])
        bullets = (await self._repo.bullet_ids_by_worklog([worklog_id])).get(worklog_id, [])
        return to_record(entry, tags, source_ids, bullets)

    async def list_entries(
        self, user_id: str, *, include_archived: bool = False, limit: int = DEFAULT_LIST_LIMIT
    ) -> list[WorklogSummary]:
        """List entries newest-first; active-only by default (archived are hidden)."""
        pk = _require_user_pk(user_id)
        entries = await self._repo.list_entries(pk, include_archived=include_archived, limit=limit)
        ids = [entry.id for entry in entries]
        tags = await self._repo.tag_labels_by_worklog(ids)
        sources = await self._repo.source_ids_by_worklog(ids)
        return [
            to_summary(entry, tags.get(entry.id, []), sources.get(entry.id, []))
            for entry in entries
        ]

    async def update(
        self, user_id: str, worklog_id: int, actor: Actor, write: WorklogWrite
    ) -> WorklogRecord:
        """Overwrite fields, tags, and attachments; re-embed only if content changed."""
        pk = _require_user_pk(user_id)
        entry = await self._repo.get(pk, worklog_id)
        if entry is None:
            raise _not_found(worklog_id)
        source_ids = dedupe(write.source_ids)
        await self._require_owned_sources(pk, source_ids)
        labels = normalize_labels(write.tags)
        new_hash = compute_content_hash(write.title, write.description)
        content_changed = new_hash != entry.content_hash
        async with transaction(self._session):
            entry.title = write.title
            entry.entry_date = write.entry_date
            entry.description = write.description
            entry.content_hash = new_hash
            await self._attach(entry.id, pk, labels, source_ids)
            # Signal a re-embed (carry the new hash) only when the content changed;
            # a tags/sources/date-only edit leaves the hash and publishes no trigger.
            metadata = {REEMBED_CONTENT_HASH_KEY: new_hash} if content_changed else None
            await self._publish(
                pk,
                actor,
                entry.id,
                Action.UPDATE,
                summary=_edited_summary(entry),
                metadata=metadata,
            )
        return await self._record_after_write(entry, labels, source_ids)

    async def archive(self, user_id: str, worklog_id: int, actor: Actor) -> WorklogRecord:
        """Soft-archive: stamp ``archived_at`` so the entry drops from active reads."""
        pk = _require_user_pk(user_id)
        entry = await self._repo.get(pk, worklog_id)
        if entry is None:
            raise _not_found(worklog_id)
        if entry.archived_at is not None:
            raise Conflict("This worklog entry is already archived.")
        async with transaction(self._session):
            entry.archived_at = self._clock()
            await self._publish(
                pk, actor, entry.id, Action.ARCHIVE, summary=_archived_summary(entry)
            )
        return await self._record_after_write(entry)

    async def restore(self, user_id: str, worklog_id: int, actor: Actor) -> WorklogRecord:
        """Clear ``archived_at`` so an archived entry returns to active reads."""
        pk = _require_user_pk(user_id)
        entry = await self._repo.get(pk, worklog_id)
        if entry is None:
            raise _not_found(worklog_id)
        if entry.archived_at is None:
            raise Conflict("This worklog entry is not archived.")
        async with transaction(self._session):
            entry.archived_at = None
            await self._publish(
                pk, actor, entry.id, Action.RESTORE, summary=_restored_summary(entry)
            )
        return await self._record_after_write(entry)

    async def add_tag(
        self, user_id: str, worklog_id: int, actor: Actor, label: str
    ) -> WorklogRecord:
        """Add one tag label to an entry (idempotent); create it if new, reuse if existing.

        A partial mutation: it reconciles only the one label against the entry's
        current tag set and leaves title, date, description, and sources untouched,
        so the content hash is unchanged and no re-embed is signalled. Adding a
        label the entry already carries is a no-op success returning the entry.
        """
        return await self._mutate_tags(
            user_id, worklog_id, actor, label, _with_label, _tag_added_summary
        )

    async def remove_tag(
        self, user_id: str, worklog_id: int, actor: Actor, label: str
    ) -> WorklogRecord:
        """Remove one tag label's edge from an entry (idempotent); never delete the tag row.

        Drops only the entry-to-tag edge, so a label another entry still uses
        survives. Removing a label the entry does not carry is a no-op success. Like
        :meth:`add_tag` it leaves the content hash, so no re-embed is signalled.
        """
        return await self._mutate_tags(
            user_id, worklog_id, actor, label, _without_label, _tag_removed_summary
        )

    async def list_tags(self, user_id: str) -> list[TagRead]:
        """List the user's tags for reuse; color is derived from the label downstream."""
        pk = _require_user_pk(user_id)
        tags = await self._repo.list_tags(pk)
        return [to_tag_read(tag) for tag in tags]

    async def _mutate_tags(
        self,
        user_id: str,
        worklog_id: int,
        actor: Actor,
        label: str,
        reconcile: Callable[[list[str], str], list[str]],
        summarize: Callable[[WorklogEntry, str], str],
    ) -> WorklogRecord:
        """Reconcile one normalized label onto an entry's tag set and record an UPDATE.

        The generic core behind :meth:`add_tag` / :meth:`remove_tag`: the caller
        injects how the label folds into the current set (``reconcile``) and how the
        event reads (``summarize``). Loads the entry user-scoped (404 if not owned),
        rejects a blank label, then writes the new tag set and publishes exactly one
        :class:`WriteEvent` (UPDATE, no re-embed) inside the transaction.
        """
        pk = _require_user_pk(user_id)
        entry = await self._repo.get(pk, worklog_id)
        if entry is None:
            raise _not_found(worklog_id)
        normalized = _require_label(label)
        current = (await self._repo.tag_labels_by_worklog([worklog_id])).get(worklog_id, [])
        labels = reconcile(current, normalized)
        async with transaction(self._session):
            await self._set_tag_labels(entry.id, pk, labels)
            await self._publish(
                pk, actor, entry.id, Action.UPDATE, summary=summarize(entry, normalized)
            )
        return await self._record_after_write(entry, labels)

    async def _attach(
        self, worklog_id: int, user_pk: int, labels: list[str], source_ids: list[int]
    ) -> None:
        """Reconcile the entry's tag and source edges to exactly the submitted sets."""
        await self._set_tag_labels(worklog_id, user_pk, labels)
        await self._repo.set_sources(worklog_id, source_ids)

    async def _set_tag_labels(self, worklog_id: int, user_pk: int, labels: list[str]) -> None:
        """Resolve labels to tags (create-or-reuse) and set the entry's tag edges to them."""
        tags = [await self._repo.get_or_create_tag(user_pk, label) for label in labels]
        await self._repo.set_tags(worklog_id, [tag.id for tag in tags])

    async def _require_owned_sources(self, user_pk: int, source_ids: list[int]) -> None:
        owned = await self._repo.owned_source_ids(user_pk, source_ids)
        missing = [source_id for source_id in source_ids if source_id not in owned]
        if missing:
            raise Validation(
                "One or more attached sources do not exist or are not yours.",
                fields={"source_ids": f"Unknown source id(s): {missing}."},
            )

    async def _record_after_write(
        self,
        entry: WorklogEntry,
        labels: list[str] | None = None,
        source_ids: list[int] | None = None,
    ) -> WorklogRecord:
        """Build the read record after a write, reflecting the entry's current edges.

        Archive/restore do not change edges, so they re-read them; create/update
        pass the sets they just wrote to avoid a redundant round trip.
        """
        worklog_id = entry.id
        if labels is None:
            labels = (await self._repo.tag_labels_by_worklog([worklog_id])).get(worklog_id, [])
        if source_ids is None:
            source_ids = (await self._repo.source_ids_by_worklog([worklog_id])).get(worklog_id, [])
        bullets = (await self._repo.bullet_ids_by_worklog([worklog_id])).get(worklog_id, [])
        return to_record(entry, sorted(labels), sorted(source_ids), bullets)

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


def _require_user_pk(user_id: str) -> int:
    """Cast the resolved string identity to the bigint PK, or reject as stale."""
    try:
        return int(user_id)
    except ValueError as exc:
        raise Unauthorized("Session is invalid or expired.") from exc


def _require_label(label: str) -> str:
    """Normalize one label and reject a blank/whitespace-only one.

    ``min_length`` on the wire schema rejects an empty string, but a whitespace-only
    label survives it and normalizes to nothing, so the service is the last guard.
    """
    normalized = normalize_labels([label])
    if not normalized:
        raise Validation(
            "A tag label cannot be blank.",
            fields={"label": "Provide a non-blank label."},
        )
    return normalized[0]


def _with_label(current: list[str], label: str) -> list[str]:
    """The current tag set with ``label`` added; unchanged if it already carries it."""
    return current if label in current else [*current, label]


def _without_label(current: list[str], label: str) -> list[str]:
    """The current tag set with ``label`` dropped; unchanged if it is absent."""
    return [existing for existing in current if existing != label]


def _not_found(worklog_id: int) -> NotFound:
    # 404-over-403: an entry another account owns is scoped out of the read, so a
    # miss is indistinguishable from "does not exist" (no existence leak).
    return NotFound(f"No worklog entry with id {worklog_id}.")


def _created_summary(write: WorklogWrite) -> str:
    return f"Added worklog “{write.title}”"


def _edited_summary(entry: WorklogEntry) -> str:
    return f"Edited worklog “{entry.title}”"


def _archived_summary(entry: WorklogEntry) -> str:
    return f"Archived worklog “{entry.title}”"


def _restored_summary(entry: WorklogEntry) -> str:
    return f"Restored worklog “{entry.title}”"


def _tag_added_summary(entry: WorklogEntry, label: str) -> str:
    return f"Tagged worklog “{entry.title}” “{label}”"


def _tag_removed_summary(entry: WorklogEntry, label: str) -> str:
    return f"Untagged worklog “{entry.title}” “{label}”"
