"""Injection seams for the resume domain: the clock and the item-id factory.

``ResumeService`` stamps timestamps through an injected clock and mints new item
ids through an injected factory, so both are assertable under pinned test doubles
(a fixed clock, a deterministic id sequence) without patching. The defaults
reproduce the ambient calls: :func:`utcnow` (``datetime.now(UTC)``) and
:func:`new_hex_id` (a random uuid4 hex). Resume row ids and the create/update
timestamps are minted by the database (a server identity column and column server
defaults), so they are not decided here.
"""

from __future__ import annotations

from floresu.core.clock import Clock, utcnow
from floresu.core.ids import IdFactory, new_hex_id

__all__ = ["Clock", "IdFactory", "new_hex_id", "utcnow"]
