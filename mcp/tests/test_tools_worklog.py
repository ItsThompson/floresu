"""Worklog read-tool output shaping.

Asserts each worklog read tool maps its backend response to the lean shape the
agent receives: the timeline summary, the single-entry record with its framing
bullets, and the tag reuse list. The shared boundary contract (one call, identity,
readOnly, error mapping) lives in ``test_tools_read``.
"""

from __future__ import annotations

import httpx

from tests.mcp_harness import AgentHarness
from tests.read_fixtures import tag, worklog_record, worklog_summary


def test_worklog_query_forwards_include_archived_and_returns_summaries() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=[worklog_summary()]))
    with harness.open() as client:
        result = harness.call_tool(client, "worklog_query", {"include_archived": True})

    assert result["isError"] is False
    assert harness.captured[0].url.params.get("include_archived") == "true"
    rows = result["structuredContent"]["result"]
    assert [row["id"] for row in rows] == [3]
    assert rows[0]["tags"] == ["backend", "search"]
    assert rows[0]["source_ids"] == [1]


def test_worklog_get_returns_entry_with_sources_tags_and_framing_bullets() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=worklog_record()))
    with harness.open() as client:
        result = harness.call_tool(client, "worklog_get", {"worklog_id": 3})

    entry = result["structuredContent"]
    assert entry["id"] == 3
    assert entry["tags"] == ["backend", "search"]
    assert entry["source_ids"] == [1]
    assert entry["bullet_ids"] == [7, 8]


def test_list_tags_returns_the_reuse_labels() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=[tag(), tag(id=12, label="search")]))
    with harness.open() as client:
        result = harness.call_tool(client, "list_tags", {})

    labels = [entry["label"] for entry in result["structuredContent"]["result"]]
    assert labels == ["backend", "search"]
