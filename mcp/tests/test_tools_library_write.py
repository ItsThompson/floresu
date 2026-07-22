"""Library write-tool behavior: scope edits, promote, and archive.

The shared boundary contract lives in ``test_tools_write``; this module asserts the
library specifics: ``bullet_update`` requires an explicit scope (omitting it is a
validation error before any internal call), an ``everywhere`` edit carries the
bullet revision and re-embeds (embed-write budget) while a ``this_resume`` fork
carries the resume revision and does not, ``bullet_promote`` carries the resume
``If-Match`` and mints an embeddable bullet, and each returns the right shape.
"""

from __future__ import annotations

import json

import httpx

from tests.mcp_harness import AgentHarness
from tests.read_fixtures import bullet, resume_record
from tests.write_fixtures import edited_everywhere, forked_this_resume


def _body(harness: AgentHarness) -> dict[str, object]:
    parsed: dict[str, object] = json.loads(harness.captured[0].content or b"{}")
    return parsed


def test_bullet_create_returns_the_record_and_uses_the_embed_budget() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(201, json=bullet()))
    with harness.open() as client:
        result = harness.call_tool(
            client, "bullet_create", {"bullet": {"text": "Cut p99 40%", "worklog_ids": [3]}}
        )

    assert result["isError"] is False
    assert result["structuredContent"]["id"] == 7
    assert harness.store.counts["ratelimit:embed_write:user-42"] == 1


def test_bullet_update_everywhere_carries_the_bullet_revision_and_re_embeds() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=edited_everywhere()))
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "bullet_update",
            {
                "edit": {
                    "bullet_id": 7,
                    "new_text": "Cut p99 latency by 45%",
                    "scope": "everywhere",
                    "if_match_bullet_revision": 4,
                }
            },
        )

    assert result["isError"] is False
    body = _body(harness)
    assert body["scope"] == "everywhere"
    assert body["if_match_bullet_revision"] == 4
    # An everywhere edit re-embeds the canonical bullet, so it uses the embed budget.
    assert harness.store.counts["ratelimit:embed_write:user-42"] == 1
    # A union return arrives under structuredContent["result"].
    outcome = result["structuredContent"]["result"]
    assert outcome["outcome"] == "edited_everywhere"
    assert outcome["bullet"]["id"] == 7


def test_bullet_update_this_resume_forks_locally_without_the_embed_budget() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=forked_this_resume()))
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "bullet_update",
            {
                "edit": {
                    "bullet_id": 7,
                    "new_text": "Cut p99 latency by 45%",
                    "scope": "this_resume",
                    "resume_id": 4,
                    "if_match_resume_revision": 6,
                }
            },
        )

    assert result["isError"] is False
    body = _body(harness)
    assert body["scope"] == "this_resume"
    assert body["resume_id"] == 4
    assert body["if_match_resume_revision"] == 6
    # A this_resume fork writes non-embedded local text: no embed-write budget spend.
    assert "ratelimit:embed_write:user-42" not in harness.store.counts
    outcome = result["structuredContent"]["result"]
    assert outcome["outcome"] == "forked_this_resume"
    assert outcome["resume"]["id"] == 4


def test_bullet_update_without_scope_is_a_validation_error_before_the_backend() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=edited_everywhere()))
    with harness.open() as client:
        result = harness.call_tool(
            client, "bullet_update", {"edit": {"bullet_id": 7, "new_text": "n"}}
        )

    assert result["isError"] is True
    # An omitted scope is rejected as invalid input; no internal call is made.
    assert harness.captured == []


def test_bullet_promote_carries_the_resume_if_match_and_uses_the_embed_budget() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=resume_record()))
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "bullet_promote",
            {"resume_id": 4, "item_id": "it-2", "if_match_resume_revision": 6},
        )

    assert result["isError"] is False
    request = harness.captured[0]
    assert request.url.path == "/resumes/4/items/it-2/promote"
    assert request.headers["If-Match"] == "6"
    # Promote mints a new canonical bullet and enqueues embedding.
    assert harness.store.counts["ratelimit:embed_write:user-42"] == 1


def test_bullet_archive_returns_the_bullet() -> None:
    harness = AgentHarness(
        lambda _r: httpx.Response(200, json=bullet(archived_at="2026-07-21T00:00:00Z"))
    )
    with harness.open() as client:
        result = harness.call_tool(client, "bullet_archive", {"bullet_id": 7})

    assert result["isError"] is False
    assert result["structuredContent"]["id"] == 7
    assert "ratelimit:embed_write:user-42" not in harness.store.counts
