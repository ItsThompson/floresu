"""Per-tool scope enforcement + agent identity/actor resolution.

The bearer boundary (:mod:`floresu_mcp.auth`) validates the token and stashes the
resolved :class:`~floresu_mcp.tokens.VerifiedAgentToken` (carrying its ``sub``,
granted ``client_id``, and ``scope``) on ``request.state`` before any tool runs.
Every tool then opens with :func:`require_scope`, which is the **one** way to
obtain the request's identity: fusing identity resolution with the scope check
means a tool cannot be written that skips authorization.

:func:`require_scope` yields ``(user_id, actor)`` from the validated token, never
from a tool argument: ``user_id`` is the token ``sub`` and ``actor`` is the
granted ``client_id`` (the named-agent label the internal client forwards as
``X-Actor``). Floresu grants a single full read-write scope
(:data:`~floresu_mcp.config.SCOPE_FULL`); a token lacking it raises a
model-recoverable :class:`ToolError` (``insufficient_scope``) naming the missing
scope, so the agent can re-authorize and retry rather than crashing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.session import ServerSession
from starlette.requests import Request

from floresu_mcp.logging import get_logger
from floresu_mcp.settings import SERVICE
from floresu_mcp.state import get_request_agent

if TYPE_CHECKING:
    from floresu_mcp.tokens import VerifiedAgentToken

_log = get_logger(SERVICE)

# The Context the framework injects; the third param is the Starlette request
# carrying the identity the bearer boundary resolved onto ``request.state``.
AgentContext = Context[ServerSession, object, Request]


def _resolve_agent(ctx: AgentContext) -> VerifiedAgentToken:
    """Return the principal the bearer boundary resolved for this request.

    Fails closed with a :class:`ToolError` if the identity is somehow absent (a
    tool reached without the guard middleware), so a call can never run
    unauthenticated. Once resolved, binds ``user_id`` into contextvars so every
    subsequent line for this tool call carries it."""
    request = ctx.request_context.request
    principal = get_request_agent(request)
    if principal is None:
        _log.warning("unauthenticated", reason="no_verified_identity")
        raise ToolError("unauthenticated: no verified agent identity on the request.")
    structlog.contextvars.bind_contextvars(user_id=principal.user_id)
    return principal


def require_scope(ctx: AgentContext, scope: str) -> tuple[str, str]:
    """Enforce that the request's token grants ``scope``; return ``(user_id, actor)``.

    This is the shared gate every tool opens with. Identity is resolved from the
    validated bearer (never a tool argument): ``user_id`` is the token ``sub`` and
    ``actor`` is the granted ``client_id``. The granted scope set is checked; a
    missing scope raises a model-recoverable :class:`ToolError` the agent can act
    on and is logged at ``warning`` (never the raw token)."""
    principal = _resolve_agent(ctx)
    granted = set(principal.scope.split())
    if scope not in granted:
        have = principal.scope or "(none)"
        _log.warning(
            "insufficient_scope",
            reason="missing_required_scope",
            required=scope,
            client_id=principal.client_id,
        )
        raise ToolError(
            f"insufficient_scope: this tool requires the '{scope}' OAuth scope, but the "
            f"token grants [{have}]. Re-authorize the agent with '{scope}' and retry."
        )
    return principal.user_id, principal.client_id
