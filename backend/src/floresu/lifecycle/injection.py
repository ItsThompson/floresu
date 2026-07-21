"""Injection seam for the lifecycle domain: the clock.

``LifecycleService`` stamps the ``exported_at`` timestamp of an export archive
through an injected clock, so a pinned clock makes the archive assertable without
wall-clock flakiness. The default reproduces the ambient call, :func:`utcnow`
(``datetime.now(UTC)``). All row ids and audit timestamps are minted by the
database, so they are not decided here.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

Clock = Callable[[], datetime]


def utcnow() -> datetime:
    """Behavior-preserving default clock: the current UTC wall-clock time."""
    return datetime.now(UTC)
