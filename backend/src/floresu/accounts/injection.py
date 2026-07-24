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

from floresu.core.clock import Clock, utcnow
from floresu.core.ids import IdFactory, new_hex_id

__all__ = ["Clock", "IdFactory", "new_hex_id", "utcnow"]
