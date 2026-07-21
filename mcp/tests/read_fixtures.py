"""Canonical backend payloads + a path router for the read-tool tests.

The read tools are thin adapters over the internal API, so their tests drive the
mounted tools through the real transport (:class:`AgentHarness`) against a backend
that returns these canonical wire payloads. The factories build valid backend
projections (overridable per test); :func:`route_backend` dispatches a request to
the payload for its path, so a single harness can answer any read route for the
surface-wide assertions (one internal call, identity + actor forwarded, no
bearer, ``readOnlyHint``).
"""

from __future__ import annotations

from typing import Any

import httpx


def worklog_summary(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": 3,
        "title": "Shipped the search DAG",
        "entry_date": "2026-01-02",
        "description": "hybrid retrieval",
        "tags": ["backend", "search"],
        "source_ids": [1],
        "archived_at": None,
    }
    return {**base, **overrides}


def worklog_record(**overrides: Any) -> dict[str, Any]:
    return {**worklog_summary(), "bullet_ids": [7, 8], **overrides}


def tag(**overrides: Any) -> dict[str, Any]:
    return {"id": 11, "label": "backend", **overrides}


def role_summary(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": 1,
        "kind": "role",
        "display_label": "Staff Engineer, Acme",
        "date_start": "2022-01-01",
        "date_end": None,
        "summary": "Platform work",
        "sort_order": 0,
        "archived_at": None,
    }
    return {**base, **overrides}


def role_record(**overrides: Any) -> dict[str, Any]:
    detail = {
        "company": "Acme",
        "job_title": "Staff Engineer",
        "title_aliases": ["SE"],
        "location": "Remote",
    }
    return {**role_summary(), "detail": detail, **overrides}


def skill(**overrides: Any) -> dict[str, Any]:
    base = {"id": 5, "name": "Python", "usage_count": 3, "sort_order": 1, "archived_at": None}
    return {**base, **overrides}


def identity_variant(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": 2,
        "label": "default",
        "full_name": "Ada Lovelace",
        "contact": {"email": "ada@example.com", "phone": None, "location": "London"},
        "links": [{"label": "site", "url": "https://ada.example.com"}],
        "is_default": True,
        "archived_at": None,
    }
    return {**base, **overrides}


def bullet(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": 7,
        "text": "Cut p99 latency 40%",
        "source_ids": [1],
        "worklog_ids": [3],
        "used_in_count": 2,
        "revision": 4,
        "archived_at": None,
    }
    return {**base, **overrides}


def resume_summary(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": 4,
        "kind": "living",
        "status": "draft",
        "title": "Living resume",
        "revision": 6,
        "schema_version": 1,
        "job_application_id": None,
        "forked_from_resume_id": None,
        "archived_at": None,
        "updated_at": "2026-01-03T10:00:00Z",
    }
    return {**base, **overrides}


def resume_document(**overrides: Any) -> dict[str, Any]:
    base = {
        "schema_version": 1,
        "header": {"identity_variant_id": 2, "identity_snapshot": None},
        "template_id": "classic",
        "sections": [
            {
                "id": "sec-1",
                "kind": "work",
                "title": "Experience",
                "item_order": ["it-1", "it-2"],
                "items": {
                    "it-1": {"id": "it-1", "kind": "library_ref", "bullet_id": 7},
                    "it-2": {
                        "id": "it-2",
                        "kind": "local",
                        "text": "Led the migration",
                        "source_refs": {"source_ids": [1], "worklog_ids": [3]},
                        "forked_from_bullet_id": None,
                    },
                },
            }
        ],
    }
    return {**base, **overrides}


def resume_record(**overrides: Any) -> dict[str, Any]:
    return {**resume_summary(), "document": resume_document(), **overrides}


def template(**overrides: Any) -> dict[str, Any]:
    base = {"id": "classic", "name": "Classic", "description": "A clean one-column layout"}
    return {**base, **overrides}


def search_result(**overrides: Any) -> dict[str, Any]:
    base = {
        "ranked": [
            {"type": "source", "id": 1, "score": 0.9},
            {"type": "worklog", "id": 3, "score": 0.6},
            {"type": "bullet", "id": 7, "score": 0.4},
        ],
        "graph": {
            "sources": [
                {
                    "id": 1,
                    "kind": "role",
                    "label": "Staff Engineer, Acme",
                    "match_score": 0.9,
                    "score": 1.9,
                }
            ],
            "worklog": [
                {
                    "id": 3,
                    "title": "Shipped the search DAG",
                    "date": "2026-01-02",
                    "score": 0.6,
                    "source_ids": [1],
                }
            ],
            "bullets": [
                {
                    "id": 7,
                    "text": "Cut p99 latency 40%",
                    "score": 0.4,
                    "worklog_ids": [3],
                    "source_ids": [1],
                }
            ],
        },
        "notices": [],
    }
    return {**base, **overrides}


# path -> the canonical response for that GET route (single object or list). The
# search POST and any unmapped path are handled by :func:`route_backend`.
_SINGLE: dict[str, dict[str, Any]] = {
    "/worklog/3": worklog_record(),
    "/sources/1": role_record(),
    "/skills/5": skill(),
    "/identity-variants/2": identity_variant(),
    "/bullets/7": bullet(),
    "/resumes/4": resume_record(),
}
_LIST: dict[str, list[dict[str, Any]]] = {
    "/worklog": [worklog_summary()],
    "/worklog/tags": [tag()],
    "/sources": [role_summary()],
    "/skills": [skill()],
    "/identity-variants": [identity_variant()],
    "/bullets": [bullet()],
    "/resumes": [
        resume_summary(),
        resume_summary(id=5, kind="application", job_application_id=9),
    ],
    "/resumes/templates": [template()],
}


def route_backend(request: httpx.Request) -> httpx.Response:
    """Answer any read route with its canonical payload (for surface-wide tests)."""
    path = request.url.path
    if path == "/search":
        return httpx.Response(200, json=search_result())
    if path in _SINGLE:
        return httpx.Response(200, json=_SINGLE[path])
    if path in _LIST:
        return httpx.Response(200, json=_LIST[path])
    return httpx.Response(404, json={"code": "NOT_FOUND", "detail": f"no route {path}"})
