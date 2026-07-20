"""Trust boundaries: resolve one ``user_id`` at each app's edge.

The backend runs two ASGI apps and identity resolves differently at each. This
module owns the **internal** boundary; the web (session-cookie) boundary and the
inbound-identity strip on the external app are owned by the web-auth surface.

Internal boundary (:func:`require_internal_user`): the internal app is app-net
only and never tunnel-routed. It trusts the ``X-User-ID`` header, but **only**
behind a valid shared ``X-Internal-Api-Token``. The comparison is constant-time
and fails closed: a request is rejected when the token is missing, wrong, or when
the server itself has no token configured. The agent's OAuth bearer is never
forwarded past this seam; the MCP server exchanges it for these trusted headers.

The security model leans on this token plus network isolation. The token half is
enforced here; the network half is a deployment invariant (the internal app is
not published and not tunnel-routed).
"""

from __future__ import annotations

import hmac
from typing import TYPE_CHECKING

from starlette.requests import Request

from floresu.core.errors import Unauthorized
from floresu.core.headers import INTERNAL_API_TOKEN_HEADER, USER_ID_HEADER

if TYPE_CHECKING:
    from floresu.core.settings import AppSettings


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
