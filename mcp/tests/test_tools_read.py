"""Surface-wide read-tool tests: the boundary contract every read tool shares.

Drives each read tool through the mounted transport with a valid minted bearer and
asserts the invariants the ticket makes every read tool honor: annotated
``readOnlyHint``, resolves identity + actor from the token (never a tool
argument), makes exactly one internal call carrying ``X-User-ID`` / ``X-Actor``
and never the agent bearer, and emits ``mcp_tool_invocations_total``. Per-domain
output shaping is asserted in the sibling ``test_tools_*`` modules.
"""

from __future__ import annotations

from typing import Any

import pytest

from floresu_mcp.config import ACTOR_HEADER, INTERNAL_API_TOKEN_HEADER, USER_ID_HEADER
from floresu_mcp.tool_metrics import TOOL_METRICS_REGISTRY
from tests.fakes import json_error
from tests.mcp_harness import AgentHarness
from tests.read_fixtures import route_backend

# tool name, arguments, expected internal method + path (the one call it must make).
_READ_CASES: list[tuple[str, dict[str, Any], str, str]] = [
    ("worklog_query", {}, "GET", "/worklog"),
    ("worklog_get", {"worklog_id": 3}, "GET", "/worklog/3"),
    ("list_tags", {}, "GET", "/worklog/tags"),
    ("profile_list", {"kind": "role"}, "GET", "/sources"),
    ("profile_get", {"kind": "role", "item_id": 1}, "GET", "/sources/1"),
    ("profile_list", {"kind": "skill"}, "GET", "/skills"),
    ("profile_get", {"kind": "skill", "item_id": 5}, "GET", "/skills/5"),
    ("profile_list", {"kind": "identity_variant"}, "GET", "/identity-variants"),
    ("profile_get", {"kind": "identity_variant", "item_id": 2}, "GET", "/identity-variants/2"),
    ("bullet_list", {}, "GET", "/bullets"),
    ("bullet_get", {"bullet_id": 7}, "GET", "/bullets/7"),
    ("resume_list", {}, "GET", "/resumes"),
    ("resume_get", {"resume_id": 4}, "GET", "/resumes/4"),
    ("list_templates", {}, "GET", "/resumes/templates"),
    ("search_experience", {"query": "staff engineer"}, "POST", "/search"),
]

_READ_TOOL_NAMES = frozenset(name for name, *_ in _READ_CASES)


def _invocations(tool: str, outcome: str) -> float:
    value = TOOL_METRICS_REGISTRY.get_sample_value(
        "mcp_tool_invocations_total", {"tool": tool, "outcome": outcome}
    )
    return value or 0.0


@pytest.mark.parametrize(("tool", "arguments", "method", "path"), _READ_CASES)
def test_read_tool_makes_one_authorized_internal_call(
    tool: str, arguments: dict[str, Any], method: str, path: str
) -> None:
    harness = AgentHarness(route_backend, sub="user-42", client_id="agent-7")
    before = _invocations(tool, "ok")
    with harness.open() as client:
        result = harness.call_tool(client, tool, arguments)

    assert result["isError"] is False
    # Exactly one internal call, to the mapped route.
    assert len(harness.captured) == 1
    request = harness.captured[0]
    assert request.method == method
    assert request.url.path == path
    # The resolved identity + actor cross the boundary; the agent bearer never does.
    assert request.headers[USER_ID_HEADER] == "user-42"
    assert request.headers[ACTOR_HEADER] == "agent-7"
    assert request.headers[INTERNAL_API_TOKEN_HEADER] == "shared-internal-token"
    assert "authorization" not in {name.lower() for name in request.headers}
    # The invocation is counted ok.
    assert _invocations(tool, "ok") == before + 1


def test_all_read_tools_declare_read_only() -> None:
    harness = AgentHarness(route_backend)
    with harness.open() as client:
        tools = {tool["name"]: tool for tool in harness.list_tools(client)}

    for name in _READ_TOOL_NAMES:
        assert tools[name]["annotations"]["readOnlyHint"] is True, name


def test_backend_error_maps_to_a_recoverable_tool_error_and_counts() -> None:
    def backend(_request: Any) -> Any:
        return json_error(409, "STALE_REVISION", "The record changed; re-read and retry.")

    harness = AgentHarness(backend)
    before = _invocations("worklog_get", "error")
    with harness.open() as client:
        result = harness.call_tool(client, "worklog_get", {"worklog_id": 3})

    assert result["isError"] is True
    text = " ".join(block.get("text", "") for block in result["content"])
    assert "STALE_REVISION" in text
    assert _invocations("worklog_get", "error") == before + 1


def test_insufficient_scope_is_rejected_before_the_backend() -> None:
    harness = AgentHarness(route_backend, scope="something:else")
    with harness.open() as client:
        result = harness.call_tool(client, "search_experience", {"query": "x"})

    assert result["isError"] is True
    text = " ".join(block.get("text", "") for block in result["content"])
    assert "insufficient_scope" in text
    # The gate rejects before any internal call.
    assert harness.captured == []
