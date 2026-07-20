"""Injection seam for the worklog domain: the clock.

``WorklogService`` stamps ``archived_at`` (and clears it on restore) through an
injected clock, so a pinned clock makes archive/restore assertable without
``sleep``. The default reproduces the ambient call, :func:`utcnow`
(``datetime.now(UTC)``). Entry and tag ids and the create/update timestamps are
minted by the database (server identity columns and column server defaults), so
they are not decided here.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

Clock = Callable[[], datetime]


def utcnow() -> datetime:
    """Behavior-preserving default clock: the current UTC wall-clock time."""
    return datetime.now(UTC)
