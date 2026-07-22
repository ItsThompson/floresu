"""Profile read-tool dispatch + typed output per kind.

The ``profile_*`` family is parameterized by kind, so these tests assert each kind
routes to the right internal endpoint and returns its correct typed shape: the
four source kinds (with typed detail on get), skill, and identity_variant. The
shared boundary contract (one call, identity, readOnly) lives in
``test_tools_read``.
"""

from __future__ import annotations

import httpx

from tests.mcp_harness import AgentHarness
from tests.read_fixtures import identity_variant, role_record, role_summary, route_backend, skill


def test_profile_get_role_returns_typed_role_detail() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=role_record()))
    with harness.open() as client:
        result = harness.call_tool(client, "profile_get", {"kind": "role", "item_id": 1})

    # A union-typed return is delivered under structuredContent["result"].
    record = result["structuredContent"]["result"]
    assert record["kind"] == "role"
    assert record["detail"]["company"] == "Acme"
    assert record["detail"]["job_title"] == "Staff Engineer"
    assert record["detail"]["title_aliases"] == ["SE"]


def test_profile_get_skill_returns_the_skill_shape() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=skill()))
    with harness.open() as client:
        result = harness.call_tool(client, "profile_get", {"kind": "skill", "item_id": 5})

    record = result["structuredContent"]["result"]
    assert record["name"] == "Python"
    assert record["usage_count"] == 3
    assert "detail" not in record


def test_profile_get_identity_variant_returns_the_variant_shape() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=identity_variant()))
    with harness.open() as client:
        result = harness.call_tool(
            client, "profile_get", {"kind": "identity_variant", "item_id": 2}
        )

    record = result["structuredContent"]["result"]
    assert record["is_default"] is True
    assert record["contact"]["email"] == "ada@example.com"
    assert record["links"][0]["url"] == "https://ada.example.com"


def test_profile_list_role_forwards_the_kind_query_param() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=[role_summary()]))
    with harness.open() as client:
        result = harness.call_tool(client, "profile_list", {"kind": "role"})

    assert harness.captured[0].url.path == "/sources"
    assert harness.captured[0].url.params.get("kind") == "role"
    assert result["structuredContent"]["result"][0]["kind"] == "role"


def test_profile_list_skill_hits_the_skills_endpoint() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=[skill()]))
    with harness.open() as client:
        result = harness.call_tool(client, "profile_list", {"kind": "skill"})

    assert harness.captured[0].url.path == "/skills"
    assert result["structuredContent"]["result"][0]["name"] == "Python"


def test_profile_list_identity_variant_hits_the_variants_endpoint() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=[identity_variant()]))
    with harness.open() as client:
        result = harness.call_tool(client, "profile_list", {"kind": "identity_variant"})

    assert harness.captured[0].url.path == "/identity-variants"
    assert result["structuredContent"]["result"][0]["label"] == "default"


def test_profile_get_rejects_an_unknown_kind_before_the_backend() -> None:
    harness = AgentHarness(route_backend)
    with harness.open() as client:
        result = harness.call_tool(client, "profile_get", {"kind": "bogus", "item_id": 1})

    assert result["isError"] is True
    assert harness.captured == []
