"""Per-request correlation via structlog contextvars.

A pure-ASGI middleware that, once per HTTP request, clears any contextvars left
over from a reused worker context and binds a ``request_id`` and the app identity
(under ``app``). ``merge_contextvars`` is already first in the structlog chain
(:mod:`floresu.core.logging`), so every subsequent log line carries the same
``request_id`` with no processor-chain change.

The middleware is **pure-ASGI**, not a ``BaseHTTPMiddleware``: the latter runs the
handler in a separate ``contextvars`` context, so bindings made here would be
invisible to the handler and the fault log. Being pure-ASGI, the bindings live in
the request's own context and survive out to the outermost 500 handler.

An inbound ``X-Request-ID`` is honored so one agent action shares an id across the
MCP -> backend hop, but it is a correlation convenience only: it is never a trust
boundary and is length/charset-bounded before use. When absent or malformed, a
fresh id is minted.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import uuid4

import structlog

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"

# Honored inbound ids are bounded to a conservative token shape so a hostile
# client cannot inject newlines, control chars, or unbounded length into a log
# field. A value outside this shape is dropped and a fresh id is minted.
_MAX_REQUEST_ID_LENGTH = 128
_REQUEST_ID_RE = re.compile(rf"[A-Za-z0-9._-]{{1,{_MAX_REQUEST_ID_LENGTH}}}")

# ASGI header names arrive lower-cased as latin-1 bytes.
_HEADER_KEY = REQUEST_ID_HEADER.lower().encode("latin-1")


def _mint_request_id() -> str:
    """Mint a fresh correlation id (32 lowercase hex chars)."""
    return uuid4().hex


def _inbound_request_id(scope: Scope) -> str | None:
    """Return a valid inbound ``X-Request-ID`` from the scope, or ``None``.

    A present-but-malformed value returns ``None`` so the caller mints a fresh id
    rather than propagating an unbounded or control-char-laden field.
    """
    for name, value in scope["headers"]:
        if name == _HEADER_KEY:
            candidate = value.decode("latin-1", "replace").strip()
            return candidate if _REQUEST_ID_RE.fullmatch(candidate) else None
    return None


class CorrelationMiddleware:
    """Bind a per-request ``request_id`` and the app identity (as ``app``) into contextvars.

    The app identity (``floresu-external`` / ``floresu-internal``) is bound under
    ``app`` so every per-request line stays attributable to the originating app
    even when both apps run in one process. The field is deliberately distinct
    from the component ``service`` bound by
    :func:`floresu.core.logging.get_logger`: a component ``service`` is already in
    the event dict before ``merge_contextvars`` runs, so its ``setdefault`` would
    drop an app tag sharing that name.
    """

    def __init__(self, app: ASGIApp, *, service: str) -> None:
        self.app = app
        self._service = service

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            # Clear first: a worker's context is reused across requests, so a
            # prior request's bindings must not leak into this one.
            structlog.contextvars.clear_contextvars()
            request_id = _inbound_request_id(scope) or _mint_request_id()
            structlog.contextvars.bind_contextvars(request_id=request_id, app=self._service)
        await self.app(scope, receive, send)
