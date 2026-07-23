"""The library side of copy-on-write: canonical bulletpoint writes for the resume.

Two resume copy-on-write paths reach into the library layer, and both must produce
a canonical-bulletpoint write that looks exactly like any other one: attributed
through the write-event seam and, when the text changes, carrying the re-embed
trigger so the bullet (re)enters the searchable corpus.

- **Edit everywhere** (``scope = everywhere``): overwrite a canonical bullet's text
  in place, guarded by the bullet's own optimistic ``revision`` so a stale edit is
  rejected, and re-queue it for embedding. Every resume that references the bullet
  picks up the new text on its next read.
- **Promote a fork** (:meth:`create_from_local`): mint a new canonical bullet from a
  resume-local item's text and provenance, ownership-checked, and queue it for
  embedding so the promoted bullet becomes searchable.

These are transaction-free primitives: the resume service calls them from inside
its own ``transaction`` boundary so the bullet write and the resume-document write
commit or roll back together. They publish through the shared seam on the caller's
session, so the audit row is transactional and the embed enqueue is deferred to
post-commit, exactly as a direct library write is. The narrow
:class:`CanonicalBulletWriter` port lets the resume service depend on this small
interface (and tests substitute an in-memory writer); the dependency is
one-directional (the library never imports the resume domain).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from floresu.core.errors import Conflict, NotFound, Validation
from floresu.core.events import (
    REEMBED_CONTENT_HASH_KEY,
    SCOPE_METADATA_KEY,
    Action,
    emit_write_event,
)
from floresu.library.config import ENTITY_TYPE
from floresu.library.hashing import compute_content_hash
from floresu.library.models import Bulletpoint
from floresu.library.schemas import BulletpointRecord, to_record
from floresu.library.summaries import created_summary, edited_summary

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.core.actor import Actor
    from floresu.core.events import WriteEventPublisher
    from floresu.library.repository import LibraryRepository

# The audit ``scope`` value recorded on an everywhere edit (mirrors the resume
# domain's ``ResumeEditScope.EVERYWHERE``; kept as a literal here so the library
# never imports the resume domain).
_SCOPE_EVERYWHERE = "everywhere"


class CanonicalBulletWriter(Protocol):
    """The narrow library capability the resume copy-on-write and promote paths need."""

    async def edit_text_everywhere(
        self, user_id: int, actor: Actor, bullet_id: int, *, new_text: str, if_match_revision: int
    ) -> BulletpointRecord: ...

    async def create_from_local(
        self,
        user_id: int,
        actor: Actor,
        *,
        text: str,
        source_ids: list[int],
        worklog_ids: list[int],
    ) -> int: ...


class LibraryCanonicalBulletWriter:
    """Canonical-bullet writes for the resume copy-on-write and promote paths.

    Transaction-free: the resume service owns the ``transaction`` boundary and
    calls these from inside it, so a bullet write commits atomically with the
    resume-document write. Publishes through the shared write-event seam on the
    caller's session, so the audit append is transactional and the embed enqueue is
    a deferred post-commit side channel, identical to a direct library write.
    """

    def __init__(
        self, session: AsyncSession, repo: LibraryRepository, publisher: WriteEventPublisher
    ) -> None:
        self._session = session
        self._repo = repo
        self._publisher = publisher

    async def edit_text_everywhere(
        self, user_id: int, actor: Actor, bullet_id: int, *, new_text: str, if_match_revision: int
    ) -> BulletpointRecord:
        """Overwrite the canonical bullet text in place, guarded by a revision CAS.

        The write is a compare-and-swap on ``revision``: a stale or raced token
        matches 0 rows and raises a recoverable re-read/retry conflict rather than
        silently overwriting, and a successful swap advances the token by one
        atomically. It signals a re-embed only when the text actually changed. This is
        the same guard ``PUT /bullets/{id}`` uses, so the two canonical edit paths
        share one token. Every resume that references the bullet resolves the new text
        on its next read, so the edit lands everywhere.
        """
        bullet = await self._repo.get(user_id, bullet_id)
        if bullet is None:
            raise NotFound(f"No bulletpoint with id {bullet_id}.")
        new_hash = compute_content_hash(new_text)
        content_changed = new_hash != bullet.content_hash
        swapped = await self._repo.update_text_if_revision(
            user_id, bullet_id, if_match_revision, new_text, new_hash
        )
        if not swapped:
            raise Conflict("This bulletpoint changed since you loaded it; re-read and retry.")
        metadata: dict[str, Any] = {SCOPE_METADATA_KEY: _SCOPE_EVERYWHERE}
        if content_changed:
            metadata[REEMBED_CONTENT_HASH_KEY] = new_hash
        await self._publish(
            user_id,
            actor,
            bullet.id,
            Action.UPDATE,
            summary=edited_summary(new_text),
            metadata=metadata,
        )
        return await self._record(bullet)

    async def create_from_local(
        self,
        user_id: int,
        actor: Actor,
        *,
        text: str,
        source_ids: list[int],
        worklog_ids: list[int],
    ) -> int:
        """Mint a canonical bullet from a resume-local fork's text and provenance.

        The framed source and worklog ids are ownership-checked (a promoted fork can
        never frame a foreign source), the content hash is computed, and the create
        is published with the re-embed trigger so the new bullet enters the corpus.
        """
        unique_sources = _unique(source_ids)
        unique_worklogs = _unique(worklog_ids)
        await self._require_owned(user_id, unique_sources, unique_worklogs)
        content_hash = compute_content_hash(text)
        bullet = Bulletpoint(user_id=user_id, text=text, content_hash=content_hash)
        await self._repo.add(bullet)
        await self._repo.set_sources(bullet.id, unique_sources)
        await self._repo.set_worklogs(bullet.id, unique_worklogs)
        await self._publish(
            user_id,
            actor,
            bullet.id,
            Action.CREATE,
            summary=created_summary(text),
            metadata={REEMBED_CONTENT_HASH_KEY: content_hash},
        )
        return bullet.id

    async def _require_owned(
        self, user_id: int, source_ids: list[int], worklog_ids: list[int]
    ) -> None:
        owned_sources = await self._repo.owned_source_ids(user_id, source_ids)
        missing_sources = [sid for sid in source_ids if sid not in owned_sources]
        if missing_sources:
            raise Validation(
                "One or more framed sources do not exist or are not yours.",
                fields={"source_ids": f"Unknown source id(s): {missing_sources}."},
            )
        owned_worklogs = await self._repo.owned_worklog_ids(user_id, worklog_ids)
        missing_worklogs = [wid for wid in worklog_ids if wid not in owned_worklogs]
        if missing_worklogs:
            raise Validation(
                "One or more framed worklog entries do not exist or are not yours.",
                fields={"worklog_ids": f"Unknown worklog id(s): {missing_worklogs}."},
            )

    async def _record(self, bullet: Bulletpoint) -> BulletpointRecord:
        source_ids = (await self._repo.source_ids_by_bullet([bullet.id])).get(bullet.id, [])
        worklog_ids = (await self._repo.worklog_ids_by_bullet([bullet.id])).get(bullet.id, [])
        return to_record(bullet, sorted(source_ids), sorted(worklog_ids))

    async def _publish(
        self,
        user_id: int,
        actor: Actor,
        entity_id: int,
        action: Action,
        *,
        summary: str,
        metadata: dict[str, Any],
    ) -> None:
        await emit_write_event(
            self._publisher,
            self._session,
            user_id=user_id,
            actor=actor,
            entity_type=ENTITY_TYPE,
            entity_id=entity_id,
            action=action,
            summary=summary,
            metadata=metadata,
        )


def _unique(ids: list[int]) -> list[int]:
    """De-duplicate ids, preserving first-seen order (a clean edge set for insert)."""
    return list(dict.fromkeys(ids))
