"""Library read-tool output shaping: canonical bulletpoints with provenance.

Asserts ``bullet_list`` / ``bullet_get`` map the backend response to the lean
bullet record (text, provenance edges, revision, usage count). The shared boundary
contract lives in ``test_tools_read``.
"""

from __future__ import annotations

import httpx

from tests.mcp_harness import AgentHarness
from tests.read_fixtures import bullet


def test_bullet_list_returns_records_with_provenance_edges() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=[bullet()]))
    with harness.open() as client:
        result = harness.call_tool(client, "bullet_list", {})

    row = result["structuredContent"]["result"][0]
    assert row["text"] == "Cut p99 latency 40%"
    assert row["source_ids"] == [1]
    assert row["worklog_ids"] == [3]
    assert row["used_in_count"] == 2
    assert row["revision"] == 4


def test_bullet_get_returns_one_bullet_with_edges() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=bullet()))
    with harness.open() as client:
        result = harness.call_tool(client, "bullet_get", {"bullet_id": 7})

    record = result["structuredContent"]
    assert record["id"] == 7
    assert record["text"] == "Cut p99 latency 40%"
    assert record["worklog_ids"] == [3]
