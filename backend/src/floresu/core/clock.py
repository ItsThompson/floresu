"""The default wall clock injected as the ``Clock`` seam across the domains.

Services decide "now" through an injected ``Clock`` so a pinned clock makes
time-dependent behavior (session expiry, archive/restore stamps, token rotation)
assertable without ``sleep`` or a negative ``timedelta``. This module is the
single home for that default and its type alias; each domain injection seam
imports them rather than redefining a byte-identical copy.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

Clock = Callable[[], datetime]


def utcnow() -> datetime:
    """The default wall clock: timezone-aware UTC now. Injected as a ``Clock`` default."""
    return datetime.now(UTC)
