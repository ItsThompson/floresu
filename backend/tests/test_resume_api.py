"""End-to-end contract tests for the /resumes surface on both app shapes.

Drives the real router, service, and write-event seam through ``TestClient`` with
the in-memory repository and resolver substituted for Postgres. Asserts the
create/read/list/update/add/remove/reorder flow, the ``If-Match`` optimistic
concurrency contract, RFC 9457 problem+json errors on the external (cookie)
boundary, and that the internal (trusted-header) boundary resolves the named-agent
actor into the published write. No database is required.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from fastapi import Request
from fastapi.testclient import TestClient

from floresu.core.actor import ActorType, resolve_internal_actor, resolve_web_actor
from floresu.core.app_factory import create_app
from floresu.core.errors import build_exception_handlers
from floresu.core.events import WriteEvent
from floresu.core.headers import ACTOR_HEADER, INTERNAL_API_TOKEN_HEADER, USER_ID_HEADER
from floresu.core.identity import SESSION_COOKIE_NAME, require_internal_user, require_user
from floresu.core.settings import AppSettings
from floresu.resumes.router import create_resumes_router
from floresu.resumes.service import ResumeService
from tests.resumes_fakes import (
    FakeSession,
    InMemoryBulletTextResolver,
    InMemoryResumeRepository,
    capturing_publisher,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

MakeSettings = Callable[..., AppSettings]

_INTERNAL_TOKEN = "internal-secret"
_INTERNAL_HEADERS = {
    INTERNAL_API_TOKEN_HEADER: _INTERNAL_TOKEN,
    USER_ID_HEADER: "1",
    ACTOR_HEADER: "claude",
}


def _client(
    make_settings: MakeSettings, *, internal: bool
) -> tuple[TestClient, InMemoryResumeRepository, InMemoryBulletTextResolver, list[WriteEvent]]:
    repo = InMemoryResumeRepository()
    resolver = InMemoryBulletTextResolver()
    publisher, captured = capturing_publisher()

    def provider(request: Request) -> ResumeService:
        return ResumeService(
            cast("AsyncSession", FakeSession()), repo, resolver, request.app.state.events
        )

    if internal:
        router = create_resumes_router(
            provider, identity=require_internal_user, actor=resolve_internal_actor
        )
        settings = make_settings(service="floresu-internal", internal_api_token=_INTERNAL_TOKEN)
    else:
        router = create_resumes_router(provider, identity=require_user, actor=resolve_web_actor)
        settings = make_settings(service="floresu-external", environment="development")

    app = create_app(settings, routers=[router], exception_handlers=build_exception_handlers())
    app.state.events = publisher

    async def verify(_cookie: str) -> str:
        return "1"

    app.state.session_verifier = verify
    client = TestClient(app)
    if not internal:
        client.cookies.set(SESSION_COOKIE_NAME, "session-token")
    return client, repo, resolver, captured


_CREATE_BLANK = {"kind": "living", "source": {"mode": "blank"}}
_SECTION = {"id": "sec-work", "kind": "work", "title": "Experience", "item_order": [], "items": {}}


def _update_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "title": "Backend Engineer",
        "template_id": "default",
        "header": {},
        "sections": [_SECTION],
    }
    body.update(overrides)
    return body


def test_create_read_and_list_a_resume(make_settings: MakeSettings) -> None:
    client, _, _, captured = _client(make_settings, internal=False)
    created = client.post("/resumes", json=_CREATE_BLANK)
    assert created.status_code == 201
    body = created.json()
    assert body["kind"] == "living"
    assert body["status"] == "draft"
    assert body["revision"] == 1
    assert body["document"]["schema_version"] == 1
    resume_id = body["id"]

    fetched = client.get(f"/resumes/{resume_id}")
    assert fetched.status_code == 200

    listed = client.get("/resumes")
    assert [row["id"] for row in listed.json()] == [resume_id]

    assert captured[-1].action.value == "create"
    assert captured[-1].actor.type is ActorType.HUMAN


def test_create_application_requires_a_job_application(make_settings: MakeSettings) -> None:
    client, _, _, _ = _client(make_settings, internal=False)
    response = client.post("/resumes", json={"kind": "application", "source": {"mode": "blank"}})
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"


def test_update_requires_if_match_and_bumps_the_revision(make_settings: MakeSettings) -> None:
    client, _, _, _ = _client(make_settings, internal=False)
    resume_id = client.post("/resumes", json=_CREATE_BLANK).json()["id"]

    # Missing If-Match is a request-validation error.
    missing = client.put(f"/resumes/{resume_id}", json=_update_body())
    assert missing.status_code == 422

    updated = client.put(f"/resumes/{resume_id}", json=_update_body(), headers={"If-Match": "1"})
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2
    assert updated.json()["title"] == "Backend Engineer"


def test_a_stale_if_match_is_a_409_conflict(make_settings: MakeSettings) -> None:
    client, _, _, _ = _client(make_settings, internal=False)
    resume_id = client.post("/resumes", json=_CREATE_BLANK).json()["id"]
    client.put(f"/resumes/{resume_id}", json=_update_body(), headers={"If-Match": "1"})

    conflict = client.put(f"/resumes/{resume_id}", json=_update_body(), headers={"If-Match": "1"})
    assert conflict.status_code == 409
    assert conflict.headers["content-type"] == "application/problem+json"


def test_add_and_remove_an_item(make_settings: MakeSettings) -> None:
    client, _, _, _ = _client(make_settings, internal=False)
    resume_id = client.post("/resumes", json=_CREATE_BLANK).json()["id"]
    client.put(f"/resumes/{resume_id}", json=_update_body(), headers={"If-Match": "1"})

    added = client.post(
        f"/resumes/{resume_id}/items",
        json={"section_id": "sec-work", "item": {"kind": "local", "text": "Shipped it."}},
        headers={"If-Match": "2"},
    )
    assert added.status_code == 200
    section = added.json()["document"]["sections"][0]
    item_id = section["item_order"][0]
    assert section["items"][item_id]["text"] == "Shipped it."

    removed = client.post(f"/resumes/{resume_id}/items/{item_id}/remove", headers={"If-Match": "3"})
    assert removed.status_code == 200
    assert removed.json()["document"]["sections"][0]["item_order"] == []


def test_reorder_items(make_settings: MakeSettings) -> None:
    client, _, _, _ = _client(make_settings, internal=False)
    resume_id = client.post("/resumes", json=_CREATE_BLANK).json()["id"]
    section = {
        "id": "sec-work",
        "kind": "work",
        "title": "Experience",
        "item_order": ["a", "b"],
        "items": {
            "a": {"id": "a", "kind": "local", "text": "one"},
            "b": {"id": "b", "kind": "local", "text": "two"},
        },
    }
    client.put(
        f"/resumes/{resume_id}", json=_update_body(sections=[section]), headers={"If-Match": "1"}
    )

    reordered = client.post(
        f"/resumes/{resume_id}/reorder",
        json={"item_orders": {"sec-work": ["b", "a"]}},
        headers={"If-Match": "2"},
    )
    assert reordered.status_code == 200
    assert reordered.json()["document"]["sections"][0]["item_order"] == ["b", "a"]


def test_not_found_resume_is_a_404_problem(make_settings: MakeSettings) -> None:
    client, _, _, _ = _client(make_settings, internal=False)
    response = client.get("/resumes/999")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


def test_unauthenticated_request_is_rejected(make_settings: MakeSettings) -> None:
    client, _, _, _ = _client(make_settings, internal=False)
    client.cookies.clear()
    assert client.get("/resumes").status_code == 401


def test_internal_boundary_attributes_the_named_agent(make_settings: MakeSettings) -> None:
    client, _, _, captured = _client(make_settings, internal=True)
    created = client.post("/resumes", json=_CREATE_BLANK, headers=_INTERNAL_HEADERS)
    assert created.status_code == 201
    assert captured[-1].actor.type is ActorType.AGENT
    assert captured[-1].actor.label == "claude"


def test_internal_boundary_rejects_a_missing_token(make_settings: MakeSettings) -> None:
    client, _, _, _ = _client(make_settings, internal=True)
    response = client.post(
        "/resumes", json=_CREATE_BLANK, headers={USER_ID_HEADER: "1", ACTOR_HEADER: "claude"}
    )
    assert response.status_code == 401
