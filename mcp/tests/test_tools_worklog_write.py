"""Worklog write-tool behavior: output shaping and the embed-write budget.

The shared boundary contract (one call, identity, hints, error mapping) lives in
``test_tools_write``; this module asserts the worklog-specific behavior: create and
update return the full record with framing bullets and consume the tighter
embed-write budget (content triggers embedding), while archive is a soft state
change that consumes only the request budget.
"""

from __future__ import annotations

import httpx

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
