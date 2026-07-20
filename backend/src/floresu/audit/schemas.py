"""Domain objects the audit service returns.

:class:`AuditEntry` is the read shape for both the activity feed and per-item
history. It carries the resolved actor (``actor_type`` plus ``actor_label``, null
for a human) and the monotonic ``id`` that orders the feed and doubles as the SSE
event id. It deliberately carries no field-level diff, only the ``action`` and its
optional ``summary`` and light ``metadata``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from floresu.core.actor import ActorType


class AuditEntry(BaseModel):
    """One audit-log row, projected for the feed and item-history reads."""

    id: int
    actor_type: ActorType
    actor_label: str | None
    entity_type: str
    entity_id: int
    action: str
    summary: str | None
    metadata: dict[str, Any] | None
    created_at: datetime
