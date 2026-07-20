"""Injection seams for the accounts domain: the clock and session-id factory.

``AccountService`` and ``SessionTokenCodec`` decide "now" and "new session id"
through injected callables, so a pinned clock makes session expiry and refresh
rotation assertable without ``sleep`` or a negative ``timedelta``. The defaults
reproduce the ambient calls: :func:`utcnow` (``datetime.now(UTC)``) and
:func:`new_hex_id` (``uuid.uuid4().hex``, used for the session ``sid``).

The user id is not minted here: ``users.id`` is a server-minted bigint identity,
so the database assigns it on insert (see :mod:`floresu.accounts.repository`).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

Clock = Callable[[], datetime]
OpaqueIdFactory = Callable[[], str]


def utcnow() -> datetime:
    """Behavior-preserving default clock: the current UTC wall-clock time."""
    return datetime.now(UTC)


def new_hex_id() -> str:
    """A uuid4 hex identifier for the session ``sid``."""
    return uuid.uuid4().hex
