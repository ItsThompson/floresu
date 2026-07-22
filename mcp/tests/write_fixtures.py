"""Canonical backend write-response payloads + a path router for the write-tool tests.

The write tools are thin adapters over the internal API, so their tests drive the
mounted tools through the real transport (:class:`AgentHarness`) against a backend
that returns these canonical wire payloads. Shared read/record payloads are reused
from :mod:`tests.read_fixtures`; this module adds the write-only shapes (scope-edit
outcomes, finalize, render reference, job application) and a
:func:`route_write_backend` dispatcher that answers any write route for the
surface-wide assertions (one internal call, identity + actor forwarded, no bearer,
correct annotations).
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from tests.read_fixtures import (
    bullet,
    identity_variant,
    resume_record,
    resume_summary,
    role_record,
    role_summary,
    skill,
    worklog_record,
)


def job_application(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": 9,
        "company": "Acme",
        "role_title": "Staff Engineer",
        "status": "added",
        "linked_resume_id": 5,
        "created_at": "2026-01-03T10:00:00Z",
        "updated_at": "2026-01-03T10:00:00Z",
    }
    return {**base, **overrides}


def finalize_result(**overrides: Any) -> dict[str, Any]:
    base = {
        "resume_id": 5,
        "status": "finalized",
        "pdf_object_key": "resumes/5/rev/3.pdf",
        "revision_no": 3,
    }
    return {**base, **overrides}


def render_reference(**overrides: Any) -> dict[str, Any]:
    base = {
        "resume_id": 4,
        "revision": 6,
        "object_key": "resumes/4/rev/6.pdf",
        "download_url": "https://r2.example.com/resumes/4/rev/6.pdf?sig=abc",
    }
    return {**base, **overrides}


def edited_everywhere(**overrides: Any) -> dict[str, Any]:
    return {"outcome": "edited_everywhere", "bullet": bullet(), **overrides}


def forked_this_resume(**overrides: Any) -> dict[str, Any]:
    return {"outcome": "forked_this_resume", "resume": resume_record(), **overrides}


def _created(payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(201, json=payload)


def _ok(payload: dict[str, Any] | list[dict[str, Any]]) -> httpx.Response:
    return httpx.Response(200, json=payload)


def _scope_edit(request: httpx.Request) -> httpx.Response:
    """Answer the copy-on-write scope edit by the scope the agent stated."""
    body = json.loads(request.content or b"{}")
    if body.get("scope") == "everywhere":
        return _ok(edited_everywhere())
    return _ok(forked_this_resume())


def route_write_backend(request: httpx.Request) -> httpx.Response:
    """Answer any write route with its canonical payload (for surface-wide tests)."""
    method = request.method
    path = request.url.path
    if path == "/resumes/bullet-edit":
        return _scope_edit(request)
    if path.endswith("/promote"):
        return _ok(resume_record())
    if path.endswith("/finalize"):
        return _ok(finalize_result())
    if path.endswith("/export"):
        return _ok(render_reference())
    if path.endswith("/remove"):
        return _ok(resume_record())
    if method == "POST" and path.endswith("/tags"):
        return _ok(worklog_record())
    if path == "/sources/reorder":
        return _ok([role_summary()])
    if path == "/skills/reorder":
        return _ok([skill()])
    if path.endswith("/archive"):
        return _ok(_ARCHIVE_BODY[_archive_group(path)])
    if method == "GET" and path == "/job-applications":
        return _ok([job_application()])
    if method == "GET" and path.startswith("/job-applications/"):
        return _ok(job_application())
    if method in {"POST", "PUT", "PATCH"}:
        return _write_by_prefix(method, path)
    return httpx.Response(404, json={"code": "NOT_FOUND", "detail": f"no route {method} {path}"})


# Archive returns the entity of the archived path's domain.
_ARCHIVE_BODY: dict[str, dict[str, Any]] = {
    "worklog": worklog_record(),
    "sources": role_record(),
    "skills": skill(),
    "identity-variants": identity_variant(),
    "bullets": bullet(),
}


def _archive_group(path: str) -> str:
    return path.strip("/").split("/")[0]


def _write_by_prefix(method: str, path: str) -> httpx.Response:
    """Route create/update writes to the canonical record of their domain."""
    if path == "/worklog" or path.startswith("/worklog/"):
        return _created(worklog_record()) if method == "POST" else _ok(worklog_record())
    if path == "/sources" or path.startswith("/sources/"):
        return (
            _created(role_record())
            if method == "POST" and path == "/sources"
            else _ok(role_record())
        )
    if path == "/skills" or path.startswith("/skills/"):
        return _created(skill()) if method == "POST" and path == "/skills" else _ok(skill())
    if path == "/identity-variants" or path.startswith("/identity-variants/"):
        return (
            _created(identity_variant())
            if method == "POST" and path == "/identity-variants"
            else _ok(identity_variant())
        )
    if path == "/bullets":
        return _created(bullet())
    if path == "/job-applications":
        return _created(job_application())
    if path.startswith("/job-applications/"):
        return _ok(job_application())
    if path == "/resumes":
        return _created(resume_record())
    if path.startswith("/resumes/"):
        return _ok(resume_record())
    return httpx.Response(404, json={"code": "NOT_FOUND", "detail": f"no route {method} {path}"})


__all__ = [
    "edited_everywhere",
    "finalize_result",
    "forked_this_resume",
    "job_application",
    "render_reference",
    "resume_summary",
    "route_write_backend",
]
