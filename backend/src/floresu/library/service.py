"""LibraryService: the single home for bulletpoint lifecycle rules and transactions.

Every bulletpoint write runs here and nowhere else, so the web and agent adapters
stay thin and provenance is uniform. Each mutate wraps its work in the
``transaction`` boundary and publishes exactly one :class:`WriteEvent` through the
write-event seam from *inside* that boundary, so the audit row (the seam's
transactional consumer) commits or rolls back atomically with the content write.
The resolved :class:`Actor` (human vs named agent) is carried into every event.

Create persists the bullet text plus its ``bullet_source`` and/or ``bullet_worklog``
edges (zero, one, or many of each; both empty is allowed but ungrouped). Edit
overwrites the full representation: setting the source / worklog lists re-frames
the bullet. The content hash is recomputed on every edit and a re-embed is
signalled (the hash rides the event metadata) only when it changes; the
``revision`` token is left untouched here (the guarded scope=everywhere edit path
that increments it lands later). Archive is soft (stamps ``archived_at``; restore
clears it), so an archived bullet leaves library reads while its edges persist.
Only canonical bullets ever reach this table; a resume-local fork lives inline in
the resume document, so there is no path for one to land here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from floresu.core.db import transaction
from floresu.core.errors import Conflict, NotFound, Unauthorized, Validation
from floresu.core.events import REEMBED_CONTENT_HASH_KEY, Action, WriteEvent
from floresu.core.observability import track_failures
from floresu.library.config import DEFAULT_LIST_LIMIT, ENTITY_TYPE
from floresu.library.hashing import compute_content_hash
from floresu.library.injection import Clock, utcnow
from floresu.library.models import Bulletpoint
from floresu.library.schemas import BulletpointRecord, to_record

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.core.actor import Actor
    from floresu.core.events import WriteEventPublisher
    from floresu.library.repository import LibraryRepository
    from floresu.library.schemas import BulletpointWrite


@track_failures("library")
class LibraryService:
    """Business rules for the Library: canonical bulletpoints and provenance edges."""

    def __init__(
        self,
        session: AsyncSession,
        repo: LibraryRepository,
        publisher: WriteEventPublisher,
        *,
        clock: Clock = utcnow,
    ) -> None:
        self._session = session
        self._repo = repo
        self._publisher = publisher
        self._clock = clock

    async def create(
        self, user_id: str, actor: Actor, write: BulletpointWrite
    ) -> BulletpointRecord:
        """Create a bullet and its provenance edges atomically; queue it for embedding."""
        pk = _require_user_pk(user_id)
        source_ids = _unique(write.source_ids)
        worklog_ids = _unique(write.worklog_ids)
        await self._require_owned(pk, source_ids, worklog_ids)
        content_hash = compute_content_hash(write.text)
        bullet = Bulletpoint(user_id=pk, text=write.text, content_hash=content_hash)
        async with transaction(self._session):
            await self._repo.add(bullet)
            await self._attach(bullet.id, source_ids, worklog_ids)
            # A create always warrants embedding: carry the hash so the embed
            # consumer picks it up (a no-op until that side channel is registered).
            await self._publish(
                pk,
                actor,
                bullet.id,
                Action.CREATE,
                summary=_created_summary(write),
                metadata={REEMBED_CONTENT_HASH_KEY: content_hash},
            )
        return await self._record_after_write(bullet, source_ids, worklog_ids)

    async def get(self, user_id: str, bullet_id: int) -> BulletpointRecord:
        """Read one bullet with its framed sources and worklog entries."""
        pk = _require_user_pk(user_id)
        bullet = await self._repo.get(pk, bullet_id)
        if bullet is None:
            raise _not_found(bullet_id)
        return await self._record_after_write(bullet)

    async def list_bullets(
        self, user_id: str, *, include_archived: bool = False, limit: int = DEFAULT_LIST_LIMIT
    ) -> list[BulletpointRecord]:
        """List bullets newest-first; active-only by default (archived are hidden)."""
        pk = _require_user_pk(user_id)
        bullets = await self._repo.list_bullets(pk, include_archived=include_archived, limit=limit)
        ids = [bullet.id for bullet in bullets]
        sources = await self._repo.source_ids_by_bullet(ids)
        worklogs = await self._repo.worklog_ids_by_bullet(ids)
        return [
            to_record(bullet, sources.get(bullet.id, []), worklogs.get(bullet.id, []))
            for bullet in bullets
        ]

    async def update(
        self, user_id: str, bullet_id: int, actor: Actor, write: BulletpointWrite
    ) -> BulletpointRecord:
        """Overwrite text and edges; re-embed only when the bullet text changed."""
        pk = _require_user_pk(user_id)
        bullet = await self._repo.get(pk, bullet_id)
        if bullet is None:
            raise _not_found(bullet_id)
        source_ids = _unique(write.source_ids)
        worklog_ids = _unique(write.worklog_ids)
        await self._require_owned(pk, source_ids, worklog_ids)
        new_hash = compute_content_hash(write.text)
        content_changed = new_hash != bullet.content_hash
        async with transaction(self._session):
            bullet.text = write.text
            bullet.content_hash = new_hash
            await self._attach(bullet.id, source_ids, worklog_ids)
            # Signal a re-embed (carry the new hash) only when the text changed; an
            # edges-only edit leaves the hash and publishes no trigger.
            metadata = {REEMBED_CONTENT_HASH_KEY: new_hash} if content_changed else None
            await self._publish(
                pk,
                actor,
                bullet.id,
                Action.UPDATE,
                summary=_edited_summary(bullet),
                metadata=metadata,
            )
        return await self._record_after_write(bullet, source_ids, worklog_ids)

    async def archive(self, user_id: str, bullet_id: int, actor: Actor) -> BulletpointRecord:
        """Soft-archive: stamp ``archived_at`` so the bullet drops from library reads."""
        pk = _require_user_pk(user_id)
        bullet = await self._repo.get(pk, bullet_id)
        if bullet is None:
            raise _not_found(bullet_id)
        if bullet.archived_at is not None:
            raise Conflict("This bulletpoint is already archived.")
        async with transaction(self._session):
            bullet.archived_at = self._clock()
            await self._publish(
                pk, actor, bullet.id, Action.ARCHIVE, summary=_archived_summary(bullet)
            )
        return await self._record_after_write(bullet)

    async def restore(self, user_id: str, bullet_id: int, actor: Actor) -> BulletpointRecord:
        """Clear ``archived_at`` so an archived bullet returns to library reads."""
        pk = _require_user_pk(user_id)
        bullet = await self._repo.get(pk, bullet_id)
        if bullet is None:
            raise _not_found(bullet_id)
        if bullet.archived_at is None:
            raise Conflict("This bulletpoint is not archived.")
        async with transaction(self._session):
            bullet.archived_at = None
            await self._publish(
                pk, actor, bullet.id, Action.RESTORE, summary=_restored_summary(bullet)
            )
        return await self._record_after_write(bullet)

    async def _attach(self, bullet_id: int, source_ids: list[int], worklog_ids: list[int]) -> None:
        """Reconcile the bullet's source and worklog edges to exactly the submitted sets."""
        await self._repo.set_sources(bullet_id, source_ids)
        await self._repo.set_worklogs(bullet_id, worklog_ids)

    async def _require_owned(
        self, user_pk: int, source_ids: list[int], worklog_ids: list[int]
    ) -> None:
        """Reject any framed source or worklog entry the user does not own."""
        owned_sources = await self._repo.owned_source_ids(user_pk, source_ids)
        missing_sources = [sid for sid in source_ids if sid not in owned_sources]
        if missing_sources:
            raise Validation(
                "One or more framed sources do not exist or are not yours.",
                fields={"source_ids": f"Unknown source id(s): {missing_sources}."},
            )
        owned_worklogs = await self._repo.owned_worklog_ids(user_pk, worklog_ids)
        missing_worklogs = [wid for wid in worklog_ids if wid not in owned_worklogs]
        if missing_worklogs:
            raise Validation(
                "One or more framed worklog entries do not exist or are not yours.",
                fields={"worklog_ids": f"Unknown worklog id(s): {missing_worklogs}."},
            )

    async def _record_after_write(
        self,
        bullet: Bulletpoint,
        source_ids: list[int] | None = None,
        worklog_ids: list[int] | None = None,
    ) -> BulletpointRecord:
        """Build the read record after a write, reflecting the bullet's current edges.

        Archive/restore/get do not change edges, so they re-read them; create/update
        pass the sets they just wrote to avoid a redundant round trip.
        """
        bullet_id = bullet.id
        if source_ids is None:
            source_ids = (await self._repo.source_ids_by_bullet([bullet_id])).get(bullet_id, [])
        if worklog_ids is None:
            worklog_ids = (await self._repo.worklog_ids_by_bullet([bullet_id])).get(bullet_id, [])
        return to_record(bullet, sorted(source_ids), sorted(worklog_ids))

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
        await self._publisher.publish(
            self._session,
            WriteEvent(
                user_id=user_pk,
                actor=actor,
                entity_type=ENTITY_TYPE,
                entity_id=entity_id,
                action=action,
                summary=summary,
                metadata=metadata,
            ),
        )


def _unique(ids: list[int]) -> list[int]:
    """De-duplicate ids, preserving first-seen order (a clean edge set for insert)."""
    return list(dict.fromkeys(ids))


def _require_user_pk(user_id: str) -> int:
    """Cast the resolved string identity to the bigint PK, or reject as stale."""
    try:
        return int(user_id)
    except ValueError as exc:
        raise Unauthorized("Session is invalid or expired.") from exc


def _not_found(bullet_id: int) -> NotFound:
    # 404-over-403: a bullet another account owns is scoped out of the read, so a
    # miss is indistinguishable from "does not exist" (no existence leak).
    return NotFound(f"No bulletpoint with id {bullet_id}.")


def _created_summary(write: BulletpointWrite) -> str:
    return f"Added bulletpoint “{_preview(write.text)}”"


def _edited_summary(bullet: Bulletpoint) -> str:
    return f"Edited bulletpoint “{_preview(bullet.text)}”"


def _archived_summary(bullet: Bulletpoint) -> str:
    return f"Archived bulletpoint “{_preview(bullet.text)}”"


def _restored_summary(bullet: Bulletpoint) -> str:
    return f"Restored bulletpoint “{_preview(bullet.text)}”"


_PREVIEW_LIMIT = 60


def _preview(text: str) -> str:
    """A short single-line preview of the bullet text for the audit summary line."""
    single_line = " ".join(text.split())
    if len(single_line) <= _PREVIEW_LIMIT:
        return single_line
    return f"{single_line[: _PREVIEW_LIMIT - 1]}…"
