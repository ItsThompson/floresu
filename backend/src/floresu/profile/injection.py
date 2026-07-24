"""Injection seam for the profile domain: the clock.

``SourceService`` stamps ``archived_at`` (and clears it on restore) through an
injected clock, so a pinned clock makes archive/restore assertable without
``sleep``. The default reproduces the ambient call, :func:`utcnow`
(``datetime.now(UTC)``). Source ids and the create/update timestamps are minted
by the database (a server identity column and column server defaults), so they
are not decided here.
"""

from __future__ import annotations

from floresu.core.clock import Clock, utcnow

__all__ = ["Clock", "utcnow"]
