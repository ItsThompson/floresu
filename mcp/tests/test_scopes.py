"""Scope-gate tests: identity + actor resolution and authorization.

``require_scope`` is the one way a tool obtains its identity. It yields
``(user_id, actor)`` from the validated bearer the boundary stashed on the
request, rejects a token missing the required scope with a recoverable
:class:`ToolError`, and fails closed if no verified identity is present.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from starlette.requests import Request

from floresu_mcp.config import SCOPE_FULL
from floresu_mcp.scopes import AgentContext, require_scope
from floresu_mcp.state import set_request_agent
from floresu_mcp.tokens import VerifiedAgentToken


def _ctx(principal: VerifiedAgentToken | None) -> AgentContext:
    request = Request({"type": "http", "headers": [], "method": "POST", "path": "/mcp"})
    if principal is not None:
        set_request_agent(request, principal)
    return cast("AgentContext", SimpleNamespace(request_context=SimpleNamespace(request=request)))


def test_returns_user_id_and_actor_from_the_token() -> None:
    principal = VerifiedAgentToken(user_id="user-42", client_id="agent-7", scope=SCOPE_FULL)

    user_id, actor = require_scope(_ctx(principal), SCOPE_FULL)

    assert user_id == "user-42"
    assert actor == "agent-7"


def test_missing_scope_raises_a_recoverable_error() -> None:
    principal = VerifiedAgentToken(user_id="user-42", client_id="agent-7", scope="something:else")

    with pytest.raises(ToolError) as excinfo:
        require_scope(_ctx(principal), SCOPE_FULL)

    message = str(excinfo.value)
    assert "insufficient_scope" in message
    assert SCOPE_FULL in message


def test_fails_closed_when_no_identity_is_present() -> None:
    with pytest.raises(ToolError) as excinfo:
        require_scope(_ctx(None), SCOPE_FULL)

    assert "unauthenticated" in str(excinfo.value)
