"""search_experience: the one-call ranked list + scored provenance DAG.

Asserts the tool returns both the flat RRF-ranked list and the same hits rolled
into the provenance graph (sources / worklog / bullets with edges and scores), so
the agent reconstructs the hierarchy without a second call, and that the section
06 filters (including the ``date_range`` wire alias ``from``) are forwarded to the
backend. The shared boundary contract lives in ``test_tools_read``.
"""

from __future__ import annotations

import json

import httpx

from tests.mcp_harness import AgentHarness
from tests.read_fixtures import search_result


def test_search_experience_returns_ranked_list_and_scored_graph() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=search_result()))
    with harness.open() as client:
        result = harness.call_tool(client, "search_experience", {"query": "staff engineer"})

    out = result["structuredContent"]
    # The flat ranked list spans all three corpus kinds.
    assert [(hit["type"], hit["id"]) for hit in out["ranked"]] == [
        ("source", 1),
        ("worklog", 3),
        ("bullet", 7),
    ]
    # The same hits rolled into the DAG: a directly-matched source (match_score set)
    # plus worklog/bullet nodes carrying edges up to their sources.
    source = out["graph"]["sources"][0]
    assert source["id"] == 1
    assert source["match_score"] == 0.9
    assert source["score"] == 1.9
    assert out["graph"]["worklog"][0]["source_ids"] == [1]
    bullet_node = out["graph"]["bullets"][0]
    assert bullet_node["worklog_ids"] == [3]
    assert bullet_node["source_ids"] == [1]


def test_search_experience_forwards_query_and_filters_with_date_alias() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=search_result()))
    filters = {
        "kinds": ["role"],
        "tags": ["backend"],
        "layer": "library",
        "date_range": {"from": "2025-01-01", "to": "2025-12-31"},
        "limit": 10,
    }
    with harness.open() as client:
        harness.call_tool(client, "search_experience", {"query": "impact", "filters": filters})

    body = json.loads(harness.captured[0].content)
    assert body["query"] == "impact"
    assert body["filters"]["kinds"] == ["role"]
    assert body["filters"]["tags"] == ["backend"]
    assert body["filters"]["layer"] == "library"
    # The date window is sent under the wire alias "from", never the Python "from_".
    assert body["filters"]["date_range"] == {"from": "2025-01-01", "to": "2025-12-31"}


def test_search_experience_defaults_to_both_layers_when_no_filters_given() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=search_result()))
    with harness.open() as client:
        harness.call_tool(client, "search_experience", {"query": "impact"})

    body = json.loads(harness.captured[0].content)
    assert body["filters"]["layer"] == "both"
