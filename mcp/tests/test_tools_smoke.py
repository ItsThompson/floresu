"""Smoke-tool tests: the RS foundation path end to end.

Drives the mounted read + write smoke tools over the real transport with a valid
minted bearer (:class:`AgentHarness`), asserting each invokes exactly one internal
call, carries the resolved identity + actor (never the bearer), emits
``mcp_tool_invocations_total``, and maps backend/limit/scope failures to
model-recoverable tool errors.
"""

from __future__ import annotations

import httpx

from floresu_mcp.config import (
    ACTOR_HEADER,
    INTERNAL_API_TOKEN_HEADER,
    SCOPE_FULL,
    USER_ID_HEADER,
)
from floresu_mcp.ratelimit import RateLimiter
from floresu_mcp.tool_metrics import TOOL_METRICS_REGISTRY
from tests.fakes import InMemoryRateLimitStore, json_error
from tests.mcp_harness import AgentHarness

_ENTRY = {
    "id": 7,
    "title": "Shipped the RS foundation",
    "entry_date": "2026-07-20",
    "description": None,
    "tags": ["backend"],
    "source_ids": [],
    "archived_at": None,
    "bullet_ids": [],
}


def _invocations(tool: str, outcome: str) -> float:
    value = TOOL_METRICS_REGISTRY.get_sample_value(
        "mcp_tool_invocations_total", {"tool": tool, "outcome": outcome}
    )
    return value or 0.0


def test_worklog_list_makes_one_internal_call_and_counts_ok() -> None:
    def backend(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_ENTRY])

    harness = AgentHarness(backend, sub="user-42", client_id="agent-7")
    before = _invocations("worklog_list", "ok")
    with harness.open() as client:
        result = harness.call_tool(client, "worklog_list", {})

    assert result["isError"] is False
    # Exactly one internal call, carrying the resolved identity + actor and never
    # the agent bearer.
    assert len(harness.captured) == 1
    request = harness.captured[0]
    assert request.method == "GET"
    assert request.url.path == "/worklog"
    assert request.headers[USER_ID_HEADER] == "user-42"
    assert request.headers[ACTOR_HEADER] == "agent-7"
    assert request.headers[INTERNAL_API_TOKEN_HEADER] == "shared-internal-token"
    assert "authorization" not in {name.lower() for name in request.headers}
    assert _invocations("worklog_list", "ok") == before + 1


def test_worklog_create_makes_one_call_and_consumes_the_embed_write_budget() -> None:
    def backend(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json=_ENTRY)

    harness = AgentHarness(backend, sub="user-42", client_id="agent-7")
    before = _invocations("worklog_create", "ok")
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "worklog_create",
            {"entry": {"title": "Shipped the RS foundation", "entry_date": "2026-07-20"}},
        )

    assert result["isError"] is False
    assert len(harness.captured) == 1
    assert harness.captured[0].method == "POST"
    assert harness.captured[0].url.path == "/worklog"
    # A content write counts against BOTH the request and the tighter embed-write
    # budget (it triggers embedding).
    assert harness.store.counts["ratelimit:request:user-42"] == 1
    assert harness.store.counts["ratelimit:embed_write:user-42"] == 1
    assert _invocations("worklog_create", "ok") == before + 1


def test_backend_error_maps_to_a_recoverable_tool_error() -> None:
    def backend(_request: httpx.Request) -> httpx.Response:
        return json_error(409, "STALE_REVISION", "The entry changed; re-read and retry.")

    harness = AgentHarness(backend)
    before = _invocations("worklog_create", "error")
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "worklog_create",
            {"entry": {"title": "x", "entry_date": "2026-07-20"}},
        )

    assert result["isError"] is True
    text = " ".join(block.get("text", "") for block in result["content"])
    assert "STALE_REVISION" in text
    assert _invocations("worklog_create", "error") == before + 1


def test_rate_limit_trip_returns_a_slow_down_error_and_skips_the_backend() -> None:
    def backend(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_ENTRY])

    # A budget of one: the first call passes, the second trips before any backend
    # call is made (the limit is checked ahead of the internal hop).
    limiter = RateLimiter(
        InMemoryRateLimitStore(), window_seconds=60, request_budget=1, embed_write_budget=1
    )
    harness = AgentHarness(backend, limiter=limiter)
    with harness.open() as client:
        first = harness.call_tool(client, "worklog_list", {})
        second = harness.call_tool(client, "worklog_list", {})

    assert first["isError"] is False
    assert second["isError"] is True
    text = " ".join(block.get("text", "") for block in second["content"])
    assert "rate_limited" in text and "Slow down" in text
    # The tripped call made no backend request: only the first call reached it.
    assert len(harness.captured) == 1


def test_insufficient_scope_is_rejected_before_the_backend() -> None:
    def backend(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_ENTRY])

    # A token granting some other scope, not floresu:full: the gate rejects it.
    harness = AgentHarness(backend, scope="something:else")
    with harness.open() as client:
        result = harness.call_tool(client, "worklog_list", {})

    assert result["isError"] is True
    text = " ".join(block.get("text", "") for block in result["content"])
    assert "insufficient_scope" in text
    assert SCOPE_FULL in text
    assert harness.captured == []


def test_smoke_tools_declare_their_annotations() -> None:
    harness = AgentHarness(lambda _request: httpx.Response(200, json=[]))
    with harness.open() as client:
        tools = {tool["name"]: tool for tool in harness.list_tools(client)}

    assert tools["worklog_list"]["annotations"]["readOnlyHint"] is True
    assert tools["worklog_create"]["annotations"]["readOnlyHint"] is False
