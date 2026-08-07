"""Job-application tool behavior: the read pair and the submit=finalize write.

Asserts the read tools are read-only and return the linked resume id, that create
starts an application at ``added``, that ``jobapp_update`` forwards the submit
trigger, and that submitting with no linked resume surfaces the backend's
recoverable conflict.
"""

from __future__ import annotations

import json

import httpx

from tests.fakes import json_error
from tests.mcp_harness import AgentHarness
from tests.write_fixtures import job_application


def _body(harness: AgentHarness) -> dict[str, object]:
    parsed: dict[str, object] = json.loads(harness.captured[0].content or b"{}")
    return parsed


def test_jobapp_list_is_read_only_and_returns_the_linked_resume_id() -> None:
    harness = AgentHarness(
        lambda _r: httpx.Response(
            200, json=[job_application(), job_application(id=10, linked_resume_id=None)]
        )
    )
    with harness.open() as client:
        tools = {tool["name"]: tool for tool in harness.list_tools(client)}
        result = harness.call_tool(client, "jobapp_list", {})

    assert tools["jobapp_list"]["annotations"]["readOnlyHint"] is True
    assert tools["jobapp_get"]["annotations"]["readOnlyHint"] is True
    assert harness.captured[0].method == "GET"
    assert harness.captured[0].url.path == "/job-applications"
    rows = result["structuredContent"]["result"]
    assert [row["id"] for row in rows] == [9, 10]
    assert rows[0]["linked_resume_id"] == 5
    assert rows[1]["linked_resume_id"] is None


def test_jobapp_get_returns_one_application_with_its_link() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=job_application()))
    with harness.open() as client:
        result = harness.call_tool(client, "jobapp_get", {"application_id": 9})

    assert harness.captured[0].url.path == "/job-applications/9"
    assert result["structuredContent"]["linked_resume_id"] == 5


def test_jobapp_create_starts_the_application_added() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(201, json=job_application(status="added")))
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "jobapp_create",
            {"request": {"company": "Acme", "role_title": "Staff Engineer"}},
        )

    assert result["isError"] is False
    assert _body(harness) == {"company": "Acme", "role_title": "Staff Engineer"}
    assert result["structuredContent"]["status"] == "added"


def test_jobapp_update_forwards_the_submit_trigger() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=job_application(status="submitted")))
    with harness.open() as client:
        result = harness.call_tool(
            client, "jobapp_update", {"application_id": 9, "request": {"status": "submitted"}}
        )

    assert result["isError"] is False
    assert harness.captured[0].method == "PATCH"
    assert _body(harness) == {"status": "submitted"}
    assert result["structuredContent"]["status"] == "submitted"


def test_jobapp_update_submit_without_a_linked_resume_is_recoverable() -> None:
    def backend(_request: httpx.Request) -> httpx.Response:
        return json_error(
            409,
            "CONFLICT",
            "This application has no linked resume to finalize; link an application resume "
            "before submitting. The status stays added.",
        )

    harness = AgentHarness(backend)
    with harness.open() as client:
        result = harness.call_tool(
            client, "jobapp_update", {"application_id": 9, "request": {"status": "submitted"}}
        )

    assert result["isError"] is True
    text = " ".join(block.get("text", "") for block in result["content"])
    assert "no linked resume" in text
    assert "CONFLICT" in text
