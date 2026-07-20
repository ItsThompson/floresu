"""Trust boundaries: resolve one ``user_id`` at each app's edge.

The backend runs two ASGI apps and identity resolves differently at each, so both
boundaries live here side by side.

External boundary (:func:`require_user`): the external app (:8000) authenticates
humans by a signed-JWT session cookie and **strips any client-supplied
``X-User-ID``** (via :class:`StripInboundIdentityMiddleware`, wired app-wide) so a
spoofed header can never reach a handler. Cookie verification is injected as a
:data:`SessionVerifier` on ``app.state``, so the real JWT + ``sid``-blacklist
logic (see :mod:`floresu.accounts.session`) is supplied through this contract
without the seam knowing about the accounts domain.

Internal boundary (:func:`require_internal_user`): the internal app is app-net
only and never tunnel-routed. It trusts the ``X-User-ID`` header, but **only**
behind a valid shared ``X-Internal-Api-Token``. The comparison is constant-time
and fails closed: a request is rejected when the token is missing, wrong, or when
the server itself has no token configured. The agent's OAuth bearer is never
forwarded past this seam; the MCP server exchanges it for these trusted headers.

The internal security model leans on this token plus network isolation. The token
half is enforced here; the network half is a deployment invariant (the internal
app is not published and not tunnel-routed).
"""

from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, cast

import structlog

# ``require_user`` and ``require_internal_user`` are FastAPI dependencies (not
# decorated route handlers); FastAPI resolves their ``Request`` annotation at
# runtime, so it must stay a runtime import or FastAPI mistakes ``request`` for a
# query field.
from starlette.requests import Request

from floresu.core.errors import Unauthorized
from floresu.core.headers import INTERNAL_API_TOKEN_HEADER, USER_ID_HEADER
from floresu.core.logging import get_logger

if TYPE_CHECKING:
    from starlette.applications import Starlette
    from starlette.types import ASGIApp, Receive, Scope, Send

    from floresu.core.settings import AppSettings

_log = get_logger("floresu-core")

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


def _token_is_valid(configured: str, presented: str) -> bool:
    """Constant-time check of the presented internal token against the configured one.

    Fails closed when the server has no token configured, so a misconfigured
    deployment denies rather than trusts every caller. The secret comparison uses
    :func:`hmac.compare_digest`, which does not short-circuit on the first byte
    that differs, so it leaks no timing signal about how much of the token matched.
    """
    if not configured:
        return False
    return hmac.compare_digest(presented.encode("utf-8"), configured.encode("utf-8"))


def require_internal_user(request: Request) -> str:
    """Resolve the trusted ``user_id`` at the internal boundary, or reject.

    Verifies the shared internal token first, then trusts and returns the
    ``X-User-ID`` the caller asserts. Raises :class:`Unauthorized` (rendered as
    problem+json) when the token is missing/invalid/unset or when no user identity
    accompanies a valid token.
    """
    settings: AppSettings = request.app.state.settings
    presented = request.headers.get(INTERNAL_API_TOKEN_HEADER, "")
    if not _token_is_valid(settings.internal_api_token, presented):
        raise Unauthorized("Missing or invalid internal API token.")

    user_id = request.headers.get(USER_ID_HEADER, "").strip()
    if not user_id:
        raise Unauthorized("Missing trusted user identity.")
    return user_id
