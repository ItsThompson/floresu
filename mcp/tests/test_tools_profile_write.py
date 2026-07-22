"""Profile write-tool behavior: per-kind dispatch, body shaping, reorder, budget.

The shared boundary contract lives in ``test_tools_write``; this module asserts the
profile-family specifics: a source write carries its ``kind`` discriminator to
``/sources`` while skill/variant writes drop it for their own endpoints, a source
write consumes the embed-write budget (source content is embedded) while a skill
write does not, reorder builds the right per-kind body, and an identity_variant
reorder is rejected before any internal call (variants are unordered).
"""

from __future__ import annotations

import json

import httpx

from tests.mcp_harness import AgentHarness
from tests.read_fixtures import identity_variant, role_record, skill

_ROLE = {
    "kind": "role",
    "display_label": "Staff Engineer, Acme",
    "company": "Acme",
    "job_title": "Staff Engineer",
}


def _body(harness: AgentHarness) -> dict[str, object]:
    parsed: dict[str, object] = json.loads(harness.captured[0].content or b"{}")
    return parsed


def test_source_create_forwards_the_kind_discriminator_and_uses_the_embed_budget() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(201, json=role_record()))
    with harness.open() as client:
        result = harness.call_tool(client, "profile_create", {"item": _ROLE})

    assert result["isError"] is False
    body = _body(harness)
    assert body["kind"] == "role"
    assert body["company"] == "Acme"
    # A source write's summary text is embedded, so it counts against the embed budget.
    assert harness.store.counts["ratelimit:embed_write:user-42"] == 1
    # The typed detail resolves in the returned record (a union return arrives under
    # structuredContent["result"]).
    assert result["structuredContent"]["result"]["detail"]["job_title"] == "Staff Engineer"


def test_skill_create_strips_the_kind_and_does_not_use_the_embed_budget() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(201, json=skill()))
    with harness.open() as client:
        result = harness.call_tool(
            client, "profile_create", {"item": {"kind": "skill", "name": "Python"}}
        )

    assert result["isError"] is False
    assert harness.captured[0].url.path == "/skills"
    # The skill write body is just the curated name; the kind discriminator is dropped.
    assert _body(harness) == {"name": "Python"}
    assert "ratelimit:embed_write:user-42" not in harness.store.counts


def test_variant_create_strips_the_kind_and_targets_the_variants_endpoint() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(201, json=identity_variant()))
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "profile_create",
            {"item": {"kind": "identity_variant", "label": "default", "full_name": "Ada Lovelace"}},
        )

    assert result["isError"] is False
    assert harness.captured[0].url.path == "/identity-variants"
    body = _body(harness)
    assert "kind" not in body
    assert body["full_name"] == "Ada Lovelace"


def test_source_reorder_sends_the_kind_and_ordered_ids() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=[]))
    with harness.open() as client:
        result = harness.call_tool(
            client, "profile_reorder", {"kind": "project", "ordered_ids": [3, 1, 2]}
        )

    assert result["isError"] is False
    assert harness.captured[0].url.path == "/sources/reorder"
    assert _body(harness) == {"kind": "project", "source_ids": [3, 1, 2]}


def test_skill_reorder_sends_the_skill_ids() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=[]))
    with harness.open() as client:
        result = harness.call_tool(
            client, "profile_reorder", {"kind": "skill", "ordered_ids": [5, 6]}
        )

    assert result["isError"] is False
    assert harness.captured[0].url.path == "/skills/reorder"
    assert _body(harness) == {"skill_ids": [5, 6]}


def test_identity_variant_reorder_is_rejected_before_any_internal_call() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=[]))
    with harness.open() as client:
        result = harness.call_tool(
            client, "profile_reorder", {"kind": "identity_variant", "ordered_ids": [1, 2]}
        )

    assert result["isError"] is True
    text = " ".join(block.get("text", "") for block in result["content"])
    assert "identity_variant" in text
    assert "cannot be reordered" in text
    # The rejection is a pure validation guard: no internal call is made.
    assert harness.captured == []


def test_skill_update_targets_the_skill_endpoint_without_the_embed_budget() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=skill()))
    with harness.open() as client:
        result = harness.call_tool(
            client, "profile_update", {"item_id": 5, "item": {"kind": "skill", "name": "Rust"}}
        )

    assert result["isError"] is False
    assert harness.captured[0].method == "PUT"
    assert harness.captured[0].url.path == "/skills/5"
    assert _body(harness) == {"name": "Rust"}
    assert "ratelimit:embed_write:user-42" not in harness.store.counts


def test_variant_update_targets_the_variants_endpoint() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=identity_variant()))
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "profile_update",
            {
                "item_id": 2,
                "item": {"kind": "identity_variant", "label": "default", "full_name": "Ada"},
            },
        )

    assert result["isError"] is False
    assert harness.captured[0].method == "PUT"
    assert harness.captured[0].url.path == "/identity-variants/2"
    assert "kind" not in _body(harness)


def test_variant_archive_targets_the_variants_endpoint() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=identity_variant()))
    with harness.open() as client:
        result = harness.call_tool(
            client, "profile_archive", {"kind": "identity_variant", "item_id": 2}
        )

    assert result["isError"] is False
    assert harness.captured[0].url.path == "/identity-variants/2/archive"
