"""Resume write-tool behavior: the creation contract, If-Match, finalize, render.

The shared boundary contract lives in ``test_tools_write``; this module asserts the
resume specifics: the creation contract forwards kind + source + job_application_id
exactly, every existing-resume mutation carries the resume revision as the
``If-Match`` header, finalize returns the frozen result, and render returns a
reference the user can open.
"""

from __future__ import annotations

import json

import httpx

from tests.mcp_harness import AgentHarness
from tests.read_fixtures import resume_record
from tests.write_fixtures import finalize_result, render_reference


def _body(harness: AgentHarness) -> dict[str, object]:
    parsed: dict[str, object] = json.loads(harness.captured[0].content or b"{}")
    return parsed


def test_resume_create_forwards_the_living_blank_contract() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(201, json=resume_record()))
    with harness.open() as client:
        result = harness.call_tool(
            client, "resume_create", {"request": {"kind": "living", "source": {"mode": "blank"}}}
        )

    assert result["isError"] is False
    body = _body(harness)
    assert body["kind"] == "living"
    assert body["source"] == {"mode": "blank"}


def test_resume_create_forwards_the_application_from_resume_contract() -> None:
    harness = AgentHarness(
        lambda _r: httpx.Response(201, json=resume_record(kind="application", job_application_id=9))
    )
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "resume_create",
            {
                "request": {
                    "kind": "application",
                    "source": {"mode": "from_resume", "from_resume_id": 4},
                    "job_application_id": 9,
                }
            },
        )

    assert result["isError"] is False
    body = _body(harness)
    assert body["kind"] == "application"
    assert body["source"] == {"mode": "from_resume", "from_resume_id": 4}
    assert body["job_application_id"] == 9


def test_resume_update_carries_the_if_match_revision_header() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=resume_record()))
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "resume_update",
            {
                "resume_id": 4,
                "document": {"title": "T", "template_id": "classic"},
                "if_match_revision": 6,
            },
        )

    assert result["isError"] is False
    request = harness.captured[0]
    assert request.method == "PUT"
    assert request.url.path == "/resumes/4"
    assert request.headers["If-Match"] == "6"


def test_resume_item_add_carries_the_if_match_and_item_body() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=resume_record()))
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "resume_item_add",
            {
                "resume_id": 4,
                "request": {"section_id": "sec-1", "item": {"kind": "library_ref", "bullet_id": 7}},
                "if_match_revision": 6,
            },
        )

    assert result["isError"] is False
    assert harness.captured[0].headers["If-Match"] == "6"
    body = _body(harness)
    assert body["section_id"] == "sec-1"
    assert body["item"] == {"kind": "library_ref", "bullet_id": 7}


def test_resume_item_remove_and_reorder_carry_the_if_match() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=resume_record()))
    with harness.open() as client:
        removed = harness.call_tool(
            client,
            "resume_item_remove",
            {"resume_id": 4, "item_id": "it-1", "if_match_revision": 6},
        )
        reordered = harness.call_tool(
            client,
            "resume_item_reorder",
            {"resume_id": 4, "order": {"section_order": ["sec-1"]}, "if_match_revision": 7},
        )

    assert removed["isError"] is False
    assert reordered["isError"] is False
    assert harness.captured[0].url.path == "/resumes/4/items/it-1/remove"
    assert harness.captured[0].headers["If-Match"] == "6"
    assert harness.captured[1].url.path == "/resumes/4/reorder"
    assert harness.captured[1].headers["If-Match"] == "7"


def test_resume_finalize_returns_the_frozen_result() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=finalize_result()))
    with harness.open() as client:
        result = harness.call_tool(client, "resume_finalize", {"resume_id": 5})

    assert result["isError"] is False
    frozen = result["structuredContent"]
    assert frozen["status"] == "finalized"
    assert frozen["pdf_object_key"] == "resumes/5/rev/3.pdf"
    assert frozen["revision_no"] == 3


def test_resume_render_returns_a_reference_the_user_can_open() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=render_reference()))
    with harness.open() as client:
        result = harness.call_tool(client, "resume_render", {"resume_id": 4})

    assert result["isError"] is False
    reference = result["structuredContent"]
    assert reference["object_key"] == "resumes/4/rev/6.pdf"
    assert reference["download_url"].startswith("https://")
