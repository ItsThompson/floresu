"""AuditService: append one row per write, and read the feed and item history.

The single source of truth for audit rules. ``append`` is invoked by the
write-event seam as a transactional consumer, so it shares the content write's
session and its row commits atomically with the write. The read methods back the
activity feed (newest-first for a user) and per-item history (newest-first for one
``entity_type``/``entity_id``), both reflecting human and agent writes alike.

Identity crosses the read boundary as a string (the resolved ``user_id``); a
malformed value resolves to an empty result rather than raising, mirroring the
accounts repository's "no such user" handling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.audit.config import DEFAULT_FEED_LIMIT, DEFAULT_ITEM_HISTORY_LIMIT
from floresu.audit.models import AuditLog
from floresu.audit.schemas import AuditEntry
from floresu.core.logging import get_logger
from floresu.core.observability import track_failures

if TYPE_CHECKING:
    from floresu.audit.repository import AuditRepository
    from floresu.core.events import WriteEvent

_log = get_logger("floresu-audit")


@track_failures("audit")
class AuditService:
    """Business rules for the append-only audit log."""

    def __init__(self, repo: AuditRepository) -> None:
        self._repo = repo

    async def append(self, event: WriteEvent) -> AuditEntry:
        """Record exactly one audit row for a content write.

        Maps the resolved actor onto ``actor_type``/``actor_label`` (label null for
        a human) and stores the action, summary, and light metadata only: no
        field-level diff. Returns the persisted entry, whose minted ``id`` is the
        feed's ordering key and the SSE event id.
        """
        entry = AuditLog(
            user_id=event.user_id,
            actor_type=event.actor.type,
            actor_label=event.actor.label,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            action=event.action.value,
            summary=event.summary,
            event_metadata=event.metadata,
        )
        await self._repo.add(entry)
        return _to_entry(entry)

    async def activity_feed(
        self, user_id: str, *, limit: int = DEFAULT_FEED_LIMIT
    ) -> list[AuditEntry]:
        """The user's activity feed: their audit rows, newest-first."""
        pk = _as_user_pk(user_id)
        if pk is None:
            return []
        rows = await self._repo.activity_feed(pk, limit=limit)
        return [_to_entry(row) for row in rows]

    async def item_history(
        self,
        user_id: str,
        entity_type: str,
        entity_id: int,
        *,
        limit: int = DEFAULT_ITEM_HISTORY_LIMIT,
    ) -> list[AuditEntry]:
        """One item's history: rows for a single ``(entity_type, entity_id)``, newest-first."""
        pk = _as_user_pk(user_id)
        if pk is None:
            return []
        rows = await self._repo.item_history(pk, entity_type, entity_id, limit=limit)
        return [_to_entry(row) for row in rows]


def _as_user_pk(user_id: str) -> int | None:
    """Map a resolved string identity to the bigint PK, or ``None`` if malformed."""
    try:
        return int(user_id)
    except ValueError:
        return None


def _to_entry(row: AuditLog) -> AuditEntry:
    return AuditEntry(
        id=row.id,
        actor_type=row.actor_type,
        actor_label=row.actor_label,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        action=row.action,
        summary=row.summary,
        metadata=row.event_metadata,
        created_at=row.created_at,
    )
