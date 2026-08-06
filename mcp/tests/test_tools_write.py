"""Surface-wide write-tool tests: the boundary contract every write tool shares.

Drives each write tool through the mounted transport with a valid minted bearer and
asserts the invariants every write tool honors: resolves identity +
actor from the token (never a tool argument), makes exactly one internal call to the
mapped route carrying ``X-User-ID`` / ``X-Actor`` and never the agent bearer, is
annotated with the correct idempotent/destructive hints, and emits
``mcp_tool_invocations_total``. It also asserts the agent has no permanent-delete
capability and that backend failures map to recoverable tool errors. Per-domain
output shaping and behavior live in the sibling ``test_tools_*_write`` modules.
"""

from __future__ import annotations

from typing import Any

import pytest

from floresu_mcp.config import ACTOR_HEADER, INTERNAL_API_TOKEN_HEADER, SCOPE_FULL, USER_ID_HEADER
from floresu_mcp.ratelimit import RateLimiter
from floresu_mcp.tool_metrics import TOOL_METRICS_REGISTRY
from tests.fakes import InMemoryRateLimitStore, json_error
from tests.mcp_harness import AgentHarness
from tests.write_fixtures import route_write_backend

# A valid worklog write body and a minimal resume update document, reused below.
_ENTRY = {"title": "Shipped the write surface", "entry_date": "2026-07-20"}
_ROLE = {
    "kind": "role",
    "display_label": "Staff Engineer, Acme",
    "company": "Acme",
    "job_title": "SE",
}
_DOC = {"title": "Living resume", "template_id": "classic"}

# tool name, arguments, expected internal method + path, expected idempotentHint.
_WRITE_CASES: list[tuple[str, dict[str, Any], str, str, bool]] = [
    ("worklog_create", {"entry": _ENTRY}, "POST", "/worklog", False),
    ("worklog_update", {"worklog_id": 3, "entry": _ENTRY}, "PUT", "/worklog/3", True),
    ("worklog_archive", {"worklog_id": 3}, "POST", "/worklog/3/archive", True),
    (
        "worklog_tag",
        {"worklog_id": 3, "label": "backend", "action": "add"},
        "POST",
        "/worklog/3/tags",
        True,
    ),
    ("profile_create", {"item": _ROLE}, "POST", "/sources", False),
    ("profile_create", {"item": {"kind": "skill", "name": "Python"}}, "POST", "/skills", False),
    (
        "profile_create",
        {"item": {"kind": "identity_variant", "label": "default", "full_name": "Ada"}},
        "POST",
        "/identity-variants",
        False,
    ),
    ("profile_update", {"item_id": 1, "item": _ROLE}, "PUT", "/sources/1", True),
    ("profile_archive", {"kind": "role", "item_id": 1}, "POST", "/sources/1/archive", True),
    ("profile_archive", {"kind": "skill", "item_id": 5}, "POST", "/skills/5/archive", True),
    ("profile_reorder", {"kind": "role", "ordered_ids": [1, 2]}, "POST", "/sources/reorder", True),
    ("profile_reorder", {"kind": "skill", "ordered_ids": [5, 6]}, "POST", "/skills/reorder", True),
    ("bullet_create", {"bullet": {"text": "Cut p99 40%"}}, "POST", "/bullets", False),
    (
        "bullet_update",
        {
            "edit": {
                "bullet_id": 7,
                "new_text": "n",
                "scope": "everywhere",
                "if_match_bullet_revision": 4,
            }
        },
        "POST",
        "/resumes/bullet-edit",
        True,
    ),
    ("bullet_archive", {"bullet_id": 7}, "POST", "/bullets/7/archive", True),
    (
        "bullet_promote",
        {"resume_id": 4, "item_id": "it-2", "if_match_resume_revision": 6},
        "POST",
        "/resumes/4/items/it-2/promote",
        False,
    ),
    (
        "resume_create",
        {"request": {"kind": "living", "source": {"mode": "blank"}}},
        "POST",
        "/resumes",
        False,
    ),
    (
        "resume_update",
        {"resume_id": 4, "document": _DOC, "if_match_revision": 6},
        "PUT",
        "/resumes/4",
        True,
    ),
    (
        "resume_item_add",
        {
            "resume_id": 4,
            "request": {"section_id": "sec-1", "item": {"kind": "library_ref", "bullet_id": 7}},
            "if_match_revision": 6,
        },
        "POST",
        "/resumes/4/items",
        False,
    ),
    (
        "resume_item_remove",
        {"resume_id": 4, "item_id": "it-1", "if_match_revision": 6},
        "POST",
        "/resumes/4/items/it-1/remove",
        True,
    ),
    (
        "resume_item_reorder",
        {"resume_id": 4, "order": {"section_order": ["sec-1"]}, "if_match_revision": 6},
        "POST",
        "/resumes/4/reorder",
        True,
    ),
    ("resume_finalize", {"resume_id": 5}, "POST", "/resumes/5/finalize", False),
    ("resume_render", {"resume_id": 4}, "POST", "/resumes/4/export", True),
    (
        "jobapp_create",
        {"request": {"company": "Acme", "role_title": "SE"}},
        "POST",
        "/job-applications",
        False,
    ),
    (
        "jobapp_update",
        {"application_id": 9, "request": {"status": "submitted"}},
        "PATCH",
        "/job-applications/9",
        True,
    ),
]

_WRITE_TOOL_NAMES = frozenset(name for name, *_ in _WRITE_CASES)


def _invocations(tool: str, outcome: str) -> float:
    value = TOOL_METRICS_REGISTRY.get_sample_value(
        "mcp_tool_invocations_total", {"tool": tool, "outcome": outcome}
    )
    return value or 0.0


@pytest.mark.parametrize(("tool", "arguments", "method", "path", "_idem"), _WRITE_CASES)
def test_write_tool_makes_one_authorized_internal_call(
    tool: str, arguments: dict[str, Any], method: str, path: str, _idem: bool
) -> None:
    harness = AgentHarness(route_write_backend, sub="user-42", client_id="agent-7")
    before = _invocations(tool, "ok")
    with harness.open() as client:
        result = harness.call_tool(client, tool, arguments)

    assert result["isError"] is False, result
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
    assert _invocations(tool, "ok") == before + 1


def test_write_tools_declare_the_correct_hints() -> None:
    harness = AgentHarness(route_write_backend)
    with harness.open() as client:
        tools = {tool["name"]: tool for tool in harness.list_tools(client)}

    # The expected idempotentHint per tool, from the write cases (a tool appears
    # once per hint value, so a dict is unambiguous).
    expected_idem = {name: idem for name, _args, _m, _p, idem in _WRITE_CASES}
    for name, idem in expected_idem.items():
        annotations = tools[name]["annotations"]
        assert annotations["readOnlyHint"] is False, name
        assert annotations["destructiveHint"] is False, name
        assert annotations["idempotentHint"] is idem, name


def test_no_permanent_delete_tool_is_registered() -> None:
    harness = AgentHarness(route_write_backend)
    with harness.open() as client:
        names = {tool["name"] for tool in harness.list_tools(client)}

    # Agents get archive but never permanent delete: no tool may
    # permanently delete an entity, delete the account, or export data (web-only).
    forbidden = ("delete", "destroy", "purge", "erase", "account")
    offenders = [name for name in names if any(word in name for word in forbidden)]
    assert offenders == [], offenders
    # The soft-archive capability the agent does get is present.
    assert {"worklog_archive", "profile_archive", "bullet_archive"} <= names


def test_stale_write_conflict_is_a_recoverable_reread_and_retry_error() -> None:
    def backend(_request: Any) -> Any:
        return json_error(
            409,
            "CONFLICT",
            "This resume changed since you loaded it (you sent revision 6, current is 7); "
            "re-read and retry.",
        )

    harness = AgentHarness(backend)
    before = _invocations("resume_update", "error")
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "resume_update",
            {"resume_id": 4, "document": _DOC, "if_match_revision": 6},
        )

    assert result["isError"] is True
    text = " ".join(block.get("text", "") for block in result["content"])
    assert "CONFLICT" in text
    assert "re-read and retry" in text
    assert _invocations("resume_update", "error") == before + 1


def test_validation_error_maps_to_a_recoverable_actionable_error() -> None:
    def backend(_request: Any) -> Any:
        return json_error(
            422,
            "VALIDATION",
            "One or more attached sources do not exist or are not yours.",
            fields={"source_ids": "Unknown source id(s): [999]."},
        )

    harness = AgentHarness(backend)
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "worklog_create",
            {"entry": {"title": "x", "entry_date": "2026-07-20", "source_ids": [999]}},
        )

    assert result["isError"] is True
    text = " ".join(block.get("text", "") for block in result["content"])
    assert "VALIDATION" in text
    assert "source_ids" in text  # the field-level guidance reaches the agent


def test_not_found_maps_to_a_recoverable_error() -> None:
    def backend(_request: Any) -> Any:
        return json_error(404, "NOT_FOUND", "No worklog entry with id 999.")

    harness = AgentHarness(backend)
    with harness.open() as client:
        result = harness.call_tool(client, "worklog_update", {"worklog_id": 999, "entry": _ENTRY})

    assert result["isError"] is True
    text = " ".join(block.get("text", "") for block in result["content"])
    assert "NOT_FOUND" in text


def test_rate_limit_trip_returns_a_slow_down_error_and_skips_the_backend() -> None:
    # A budget of one: the first write passes, the second trips before any backend
    # call is made (the limit is checked ahead of the internal hop).
    limiter = RateLimiter(
        InMemoryRateLimitStore(), window_seconds=60, request_budget=1, embed_write_budget=5
    )
    harness = AgentHarness(route_write_backend, limiter=limiter)
    with harness.open() as client:
        first = harness.call_tool(client, "resume_render", {"resume_id": 4})
        second = harness.call_tool(client, "resume_render", {"resume_id": 4})

    assert first["isError"] is False
    assert second["isError"] is True
    text = " ".join(block.get("text", "") for block in second["content"])
    assert "rate_limited" in text and "Slow down" in text
    # The tripped call made no backend request: only the first reached it.
    assert len(harness.captured) == 1


def test_embed_write_budget_trips_independently_of_the_request_budget() -> None:
    # A generous request budget but an embed-write budget of one: the first
    # content write passes, the second trips on the tighter embed budget.
    limiter = RateLimiter(
        InMemoryRateLimitStore(), window_seconds=60, request_budget=100, embed_write_budget=1
    )
    harness = AgentHarness(route_write_backend, limiter=limiter)
    with harness.open() as client:
        first = harness.call_tool(client, "bullet_create", {"bullet": {"text": "a"}})
        second = harness.call_tool(client, "bullet_create", {"bullet": {"text": "b"}})

    assert first["isError"] is False
    assert second["isError"] is True
    text = " ".join(block.get("text", "") for block in second["content"])
    assert "embed-write" in text
    assert len(harness.captured) == 1


def test_insufficient_scope_is_rejected_before_the_backend() -> None:
    # A token granting some other scope, not floresu:full: the gate rejects it.
    harness = AgentHarness(route_write_backend, scope="something:else")
    with harness.open() as client:
        result = harness.call_tool(client, "worklog_create", {"entry": _ENTRY})

    assert result["isError"] is True
    text = " ".join(block.get("text", "") for block in result["content"])
    assert "insufficient_scope" in text
    assert SCOPE_FULL in text
    assert harness.captured == []
