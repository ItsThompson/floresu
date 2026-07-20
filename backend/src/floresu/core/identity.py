"""Identity resolution at the internet-facing trust boundary.

The external app (:8000) authenticates humans by a signed-JWT session cookie and
**strips any client-supplied ``X-User-ID``** (via
:class:`StripInboundIdentityMiddleware`, wired app-wide) so a spoofed header can
never reach a handler. Cookie verification is injected as a
:data:`SessionVerifier` on ``app.state``, so the real JWT + ``sid``-blacklist
logic (see :mod:`floresu.accounts.session`) is supplied through this contract
without the seam knowing about the accounts domain.

``require_user`` is a FastAPI dependency; external route modules declare
``Depends(require_user)``. The internal app's trusted-header boundary
(``require_internal_user``) is a separate slice and lives alongside this once it
lands.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, cast

import structlog

# ``require_user`` is a FastAPI dependency (not a decorated route handler);
# FastAPI resolves its ``Request`` annotation at runtime, so it must stay a
# runtime import or FastAPI mistakes ``request`` for a query field.
from starlette.requests import Request

from floresu.core.errors import Unauthorized
from floresu.core.logging import get_logger

if TYPE_CHECKING:
    from starlette.applications import Starlette
    from starlette.types import ASGIApp, Receive, Scope, Send

_log = get_logger("floresu-core")

# Client-supplied identity header the external app always strips; the internal
# app (a later slice) is the only place it is trusted.
USER_ID_HEADER = "X-User-ID"
SESSION_COOKIE_NAME = "floresu_session"

# The ``app.state`` attribute the external identity boundary resolves from.
SESSION_VERIFIER_ATTR = "session_verifier"

# A SessionVerifier turns a raw session-cookie value into a resolved ``user_id``,
# or ``None`` if the cookie is missing/invalid/expired. It is async so a
# per-request sid-blacklist lookup (an I/O call) runs behind this same contract
# without reworking ``require_user``.
SessionVerifier = Callable[[str], Awaitable[str | None]]


async def deny_all_sessions(_cookie: str) -> str | None:
    """Default deny-all verifier: every cookie fails to resolve, so
    :func:`require_user` fail-safe denies. Replaced by injecting a real
    ``SessionVerifier`` on ``app.state.session_verifier``."""
    return None


def get_session_verifier(app: Starlette) -> SessionVerifier:
    """The injected session verifier, or the deny-all default.

    Returns :func:`deny_all_sessions` when the seam is unset OR not callable, so a
    missing or wrong-type wiring fail-safe denies rather than raising at the auth
    boundary. Starlette's ``app.state`` launders to ``Any``, so this typed
    accessor is the one place the seam is read.
    """
    verifier = getattr(app.state, SESSION_VERIFIER_ATTR, deny_all_sessions)
    if callable(verifier):
        return cast("SessionVerifier", verifier)
    return deny_all_sessions


class StripInboundIdentityMiddleware:
    """Remove client-supplied identity headers before the external app routes.

    Wired on the external app only. A spoofed ``X-User-ID`` from the internet is
    dropped here, app-wide, so it can never reach a handler or be mistaken for a
    resolved identity: the strip is a boundary guarantee, not something each route
    must remember.
    """

    def __init__(self, app: ASGIApp, *, header: str = USER_ID_HEADER) -> None:
        self.app = app
        # ASGI header names arrive lower-cased as latin-1 bytes.
        self._blocked = header.lower().encode("latin-1")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            kept = [
                (name, value) for name, value in scope["headers"] if name.lower() != self._blocked
            ]
            scope = {**scope, "headers": kept}
        await self.app(scope, receive, send)


async def require_user(request: Request) -> str:
    """External dependency: resolve ``user_id`` from the session cookie.

    Reads only the cookie; ``X-User-ID`` is never consulted (and is stripped
    upstream by :class:`StripInboundIdentityMiddleware`). Raises ``Unauthorized``
    when no valid session resolves.
    """
    verify = get_session_verifier(request.app)
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie is None:
        _log.warning("session_invalid", reason="missing_cookie")
        raise Unauthorized("No session cookie present.")
    user_id = await verify(cookie)
    if user_id is None:
        _log.warning("session_invalid", reason="invalid_or_expired")
        raise Unauthorized("Session is invalid or expired.")
    # Bind the resolved identity so every subsequent log line for this request
    # carries user_id via merge_contextvars.
    structlog.contextvars.bind_contextvars(user_id=user_id)
    return user_id
