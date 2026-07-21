"""Injection seams for the resume domain: the clock and the item-id factory.

``ResumeService`` stamps timestamps through an injected clock and mints new item
ids through an injected factory, so both are assertable under pinned test doubles
(a fixed clock, a deterministic id sequence) without patching. The defaults
reproduce the ambient calls: :func:`utcnow` (``datetime.now(UTC)``) and
:func:`new_item_id` (a random uuid4 hex). Resume row ids and the create/update
timestamps are minted by the database (a server identity column and column server
defaults), so they are not decided here.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

Clock = Callable[[], datetime]
IdFactory = Callable[[], str]


def utcnow() -> datetime:
    """Behavior-preserving default clock: the current UTC wall-clock time."""
    return datetime.now(UTC)


def new_item_id() -> str:
    """A new document-scoped item id (server-minted; clients never set item ids)."""
    return uuid.uuid4().hex
