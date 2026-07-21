"""Resume read-tool output shaping: summaries, the full document, and templates.

Asserts ``resume_list`` returns living + application summaries (and forwards the
kind filter), ``resume_get`` returns the full versioned document with its ordered
library-ref and local items, and ``list_templates`` returns the registry entries.
The shared boundary contract lives in ``test_tools_read``.
"""

from __future__ import annotations

import httpx

from tests.mcp_harness import AgentHarness
from tests.read_fixtures import resume_record, resume_summary, template


def test_resume_list_returns_living_and_application_summaries() -> None:
    resumes = [resume_summary(), resume_summary(id=5, kind="application", job_application_id=9)]
    harness = AgentHarness(lambda _r: httpx.Response(200, json=resumes))
    with harness.open() as client:
        result = harness.call_tool(client, "resume_list", {})

    rows = result["structuredContent"]["result"]
    assert {row["kind"] for row in rows} == {"living", "application"}
    application = next(row for row in rows if row["kind"] == "application")
    assert application["job_application_id"] == 9


def test_resume_list_forwards_the_kind_filter() -> None:
    harness = AgentHarness(
        lambda _r: httpx.Response(200, json=[resume_summary(id=5, kind="application")])
    )
    with harness.open() as client:
        harness.call_tool(client, "resume_list", {"kind": "application"})

    assert harness.captured[0].url.params.get("kind") == "application"


def test_resume_get_returns_the_full_versioned_document() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=resume_record()))
    with harness.open() as client:
        result = harness.call_tool(client, "resume_get", {"resume_id": 4})

    record = result["structuredContent"]
    assert record["id"] == 4
    document = record["document"]
    assert document["template_id"] == "classic"
    section = document["sections"][0]
    assert section["item_order"] == ["it-1", "it-2"]
    assert section["items"]["it-1"]["kind"] == "library_ref"
    assert section["items"]["it-1"]["bullet_id"] == 7
    assert section["items"]["it-2"]["kind"] == "local"
    assert section["items"]["it-2"]["text"] == "Led the migration"


def test_list_templates_returns_registry_entries() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=[template()]))
    with harness.open() as client:
        result = harness.call_tool(client, "list_templates", {})

    row = result["structuredContent"]["result"][0]
    assert row["id"] == "classic"
    assert row["name"] == "Classic"
