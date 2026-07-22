"""Worklog write-tool behavior: output shaping and the embed-write budget.

The shared boundary contract (one call, identity, hints, error mapping) lives in
``test_tools_write``; this module asserts the worklog-specific behavior: create and
update return the full record with framing bullets and consume the tighter
embed-write budget (content triggers embedding), while archive is a soft state
change that consumes only the request budget. ``worklog_tag`` reconciles one label
in a single ``POST`` (never a DELETE), is idempotent, and (like archive) does not
trigger embedding, so it too consumes only the request budget.
"""

from __future__ import annotations

import json

import httpx

from floresu_mcp.ratelimit import RateLimiter
from tests.fakes import InMemoryRateLimitStore, json_error
from tests.mcp_harness import AgentHarness
from tests.read_fixtures import worklog_record

_ENTRY = {"title": "Shipped the write surface", "entry_date": "2026-07-20", "tags": ["backend"]}


def test_worklog_create_returns_the_record_and_consumes_the_embed_write_budget() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(201, json=worklog_record()))
    with harness.open() as client:
        result = harness.call_tool(client, "worklog_create", {"entry": _ENTRY})

    assert result["isError"] is False
    record = result["structuredContent"]
    assert record["id"] == 3
    assert record["bullet_ids"] == [7, 8]
    # A content write counts against BOTH the request and the tighter embed-write budget.
    assert harness.store.counts["ratelimit:request:user-42"] == 1
    assert harness.store.counts["ratelimit:embed_write:user-42"] == 1


def test_worklog_update_consumes_the_embed_write_budget() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=worklog_record()))
    with harness.open() as client:
        result = harness.call_tool(client, "worklog_update", {"worklog_id": 3, "entry": _ENTRY})

    assert result["isError"] is False
    assert harness.store.counts["ratelimit:embed_write:user-42"] == 1


def test_worklog_archive_consumes_only_the_request_budget() -> None:
    harness = AgentHarness(
        lambda _r: httpx.Response(200, json=worklog_record(archived_at="2026-07-21T00:00:00Z"))
    )
    with harness.open() as client:
        result = harness.call_tool(client, "worklog_archive", {"worklog_id": 3})

    assert result["isError"] is False
    assert harness.store.counts["ratelimit:request:user-42"] == 1
    # Archive is a soft, reversible state change: it does not trigger embedding.
    assert "ratelimit:embed_write:user-42" not in harness.store.counts


def test_worklog_tag_add_returns_the_record_and_consumes_only_the_request_budget() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=worklog_record(tags=["backend"])))
    with harness.open() as client:
        result = harness.call_tool(
            client, "worklog_tag", {"worklog_id": 3, "label": "backend", "action": "add"}
        )

    assert result["isError"] is False
    record = result["structuredContent"]
    assert record["id"] == 3
    assert record["tags"] == ["backend"]
    # A tag mutation does not change entry content, so it counts against the
    # request budget only, never the tighter embed-write budget.
    assert harness.store.counts["ratelimit:request:user-42"] == 1
    assert "ratelimit:embed_write:user-42" not in harness.store.counts


def test_worklog_tag_remove_posts_label_and_action_and_never_deletes() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=worklog_record(tags=[])))
    with harness.open() as client:
        result = harness.call_tool(
            client, "worklog_tag", {"worklog_id": 3, "label": "backend", "action": "remove"}
        )

    assert result["isError"] is False
    # Remove is a non-destructive POST carrying {label, action}; the agent never
    # issues a DELETE (the internal app exposes zero DELETE routes).
    assert len(harness.captured) == 1
    request = harness.captured[0]
    assert request.method == "POST"
    assert request.url.path == "/worklog/3/tags"
    assert json.loads(request.content) == {"label": "backend", "action": "remove"}


def test_worklog_tag_add_existing_label_is_an_idempotent_no_op_success() -> None:
    # The backend answers an add of an already-present label with 200 + the
    # unchanged entry (Ticket 6 idempotency); the tool surfaces it as a success
    # returning the current entry, not an error.
    harness = AgentHarness(lambda _r: httpx.Response(200, json=worklog_record(tags=["backend"])))
    with harness.open() as client:
        result = harness.call_tool(
            client, "worklog_tag", {"worklog_id": 3, "label": "backend", "action": "add"}
        )

    assert result["isError"] is False
    assert result["structuredContent"]["tags"] == ["backend"]


def test_worklog_tag_remove_absent_label_is_an_idempotent_no_op_success() -> None:
    # Removing a label the entry does not carry is a 200 + unchanged entry, not an
    # error: the tool returns the current entry.
    harness = AgentHarness(lambda _r: httpx.Response(200, json=worklog_record(tags=["backend"])))
    with harness.open() as client:
        result = harness.call_tool(
            client, "worklog_tag", {"worklog_id": 3, "label": "frontend", "action": "remove"}
        )

    assert result["isError"] is False
    assert result["structuredContent"]["tags"] == ["backend"]


def test_worklog_tag_on_an_unowned_entry_maps_to_a_recoverable_not_found() -> None:
    def backend(_request: httpx.Request) -> httpx.Response:
        return json_error(404, "NOT_FOUND", "No worklog entry with id 999.")

    harness = AgentHarness(backend)
    with harness.open() as client:
        result = harness.call_tool(
            client, "worklog_tag", {"worklog_id": 999, "label": "backend", "action": "add"}
        )

    assert result["isError"] is True
    text = " ".join(block.get("text", "") for block in result["content"])
    assert "NOT_FOUND" in text


def test_worklog_tag_rate_limit_trip_returns_slow_down_and_skips_the_backend() -> None:
    # A request budget of one: the first tag call passes, the second trips before
    # any backend call (the limit is checked ahead of the internal hop).
    limiter = RateLimiter(
        InMemoryRateLimitStore(), window_seconds=60, request_budget=1, embed_write_budget=5
    )
    harness = AgentHarness(lambda _r: httpx.Response(200, json=worklog_record()), limiter=limiter)
    with harness.open() as client:
        first = harness.call_tool(
            client, "worklog_tag", {"worklog_id": 3, "label": "backend", "action": "add"}
        )
        second = harness.call_tool(
            client, "worklog_tag", {"worklog_id": 3, "label": "search", "action": "add"}
        )

    assert first["isError"] is False
    assert second["isError"] is True
    text = " ".join(block.get("text", "") for block in second["content"])
    assert "rate_limited" in text and "Slow down" in text
    # The tripped call made no backend request: only the first reached it.
    assert len(harness.captured) == 1
