"""Injection seams for the OAuth AS: the clock and opaque-id factories.

The service, codec, and token-exchange layers all inject the same two seams, and
the SqlAlchemy repository is fed the *resolved* values (it never mints its own).
A pinned clock and deterministic id factory then govern the whole
mint -> park -> expire -> rotate -> revoke flow, so tests assert expiry without
``sleep`` or a negative ``timedelta``.

The defaults reproduce the ambient calls:

- :func:`new_urlsafe_id` -> ``secrets.token_urlsafe(32)``: the high-entropy opaque
  protocol identifiers (``client_id``, ``auth_request_id``, authorization ``code``).
- :func:`new_hex_id` -> ``uuid.uuid4().hex``: the internal surrogate record keys
  (``oauth_grants.id``, the access-token ``jti``).
"""

from __future__ import annotations

import secrets

from floresu.core.clock import Clock, utcnow
from floresu.core.ids import IdFactory, new_hex_id

__all__ = ["Clock", "IdFactory", "new_hex_id", "new_urlsafe_id", "utcnow"]

# Opaque protocol identifiers are high-entropy url-safe tokens (~43 chars from 32
# bytes); unguessability is defense-in-depth (authorization is by row scoping).
_URLSAFE_ID_BYTES = 32


def new_urlsafe_id() -> str:
    """A high-entropy url-safe opaque identifier (client_id, request_id, code)."""
    return secrets.token_urlsafe(_URLSAFE_ID_BYTES)
