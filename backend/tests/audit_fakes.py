"""In-memory test doubles and factories for the audit domain.

The service is tested sociably: the real :class:`AuditService` over this in-memory
repository substituted at the only true external boundary (Postgres). The fake
assigns the monotonic ``id`` and the ``created_at`` the identity column and server
default would, so the append, feed, and item-history paths are exercised without a
database. :func:`build_write_event` is the shared factory for the events the seam
and the audit service consume.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from floresu.audit.models import AuditLog
from floresu.core.actor import Actor, ActorType
from floresu.core.events import Action, WriteEvent

if TYPE_CHECKING:
    from collections.abc import Sequence


class InMemoryAuditRepository:
    """A list-backed :class:`AuditRepository` with real monotonic ids and ordering."""

    def __init__(self) -> None:
        self._rows: list[AuditLog] = []
        self._next_id = 1

    async def add(self, entry: AuditLog) -> None:
        # Mirror the identity column + created_at server default the real table
        # assigns on insert, so the service can project a complete AuditEntry.
        entry.id = self._next_id
        self._next_id += 1
        if entry.created_at is None:
            entry.created_at = datetime.now(UTC)
        self._rows.append(entry)

    async def activity_feed(self, user_id: int, *, limit: int) -> Sequence[AuditLog]:
        rows = [row for row in self._rows if row.user_id == user_id]
        return sorted(rows, key=lambda row: row.id, reverse=True)[:limit]

    async def item_history(
        self, user_id: int, entity_type: str, entity_id: int, *, limit: int
    ) -> Sequence[AuditLog]:
        rows = [
            row
            for row in self._rows
            if row.user_id == user_id
            and row.entity_type == entity_type
            and row.entity_id == entity_id
        ]
        return sorted(rows, key=lambda row: row.id, reverse=True)[:limit]


def human_actor() -> Actor:
    return Actor(type=ActorType.HUMAN)


def agent_actor(label: str = "claude") -> Actor:
    return Actor(type=ActorType.AGENT, label=label)


def build_write_event(**overrides: Any) -> WriteEvent:
    """A valid :class:`WriteEvent` with test defaults and per-test overrides."""
    base: dict[str, Any] = {
        "user_id": 1,
        "actor": human_actor(),
        "entity_type": "worklog",
        "entity_id": 100,
        "action": Action.CREATE,
        "summary": None,
        "metadata": None,
    }
    base.update(overrides)
    return WriteEvent(**base)
