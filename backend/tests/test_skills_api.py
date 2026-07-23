"""End-to-end contract tests for the /skills surface on both app shapes.

Drives the real router, service, and write-event seam through ``TestClient`` with
the in-memory repository substituted for Postgres. Asserts the create/read/list/
rename/reorder/archive flow and RFC 9457 problem+json errors on the external
(cookie) boundary, and that the internal (trusted-header) boundary resolves the
named-agent actor into the published write. No database is required.
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
from floresu.profile.skills.router import create_skills_router
from floresu.profile.skills.service import SkillService
from tests.skills_fakes import (
    InMemorySkillRepository,
    build_skill_write,
)
from tests.support.fakes import CapturingWriteEventPublisher, FakeSession

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
) -> tuple[TestClient, InMemorySkillRepository, list[WriteEvent]]:
    repo = InMemorySkillRepository()
    publisher = CapturingWriteEventPublisher()
    captured = publisher.captured

    def provider(request: Request) -> SkillService:
        return SkillService(cast("AsyncSession", FakeSession()), repo, request.app.state.events)

    if internal:
        router = create_skills_router(
            provider, identity=require_internal_user, actor=resolve_internal_actor
        )
        settings = make_settings(service="floresu-internal", internal_api_token=_INTERNAL_TOKEN)
    else:
        router = create_skills_router(provider, identity=require_user, actor=resolve_web_actor)
        settings = make_settings(service="floresu-external", environment="development")

    app = create_app(settings, routers=[router], exception_handlers=build_exception_handlers())
    app.state.events = publisher

    async def verify(_cookie: str) -> str:
        return "1"

    app.state.session_verifier = verify
    client = TestClient(app)
    if not internal:
        client.cookies.set(SESSION_COOKIE_NAME, "session-token")
    return client, repo, captured


def test_create_read_and_list_a_skill(make_settings: MakeSettings) -> None:
    client, repo, captured = _client(make_settings, internal=False)
    created = client.post("/skills", json=build_skill_write(name="Python").model_dump())
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Python"
    assert body["usage_count"] == 0
    assert body["sort_order"] == 0
    assert body["archived_at"] is None
    skill_id = body["id"]

    # Usage is a computed read: seed a tag match and the count reflects it.
    repo.set_usage(1, "Python", 4)
    fetched = client.get(f"/skills/{skill_id}")
    assert fetched.status_code == 200
    assert fetched.json()["usage_count"] == 4

    listed = client.get("/skills")
    assert listed.status_code == 200
    assert [s["id"] for s in listed.json()] == [skill_id]

    assert captured[-1].action.value == "create"
    assert captured[-1].actor.type is ActorType.HUMAN


def test_duplicate_name_is_a_409_problem(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    client.post("/skills", json=build_skill_write(name="Rust").model_dump())
    conflict = client.post("/skills", json=build_skill_write(name="Rust").model_dump())
    assert conflict.status_code == 409
    assert conflict.headers["content-type"] == "application/problem+json"


def test_missing_name_is_a_422(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    response = client.post("/skills", json={})
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"


def test_rename_edits_the_name(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    skill_id = client.post("/skills", json=build_skill_write(name="Go").model_dump()).json()["id"]
    edited = client.put(f"/skills/{skill_id}", json=build_skill_write(name="Golang").model_dump())
    assert edited.status_code == 200
    assert edited.json()["name"] == "Golang"


def test_archive_and_restore_flow(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    skill_id = client.post("/skills", json=build_skill_write().model_dump()).json()["id"]

    archived = client.post(f"/skills/{skill_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert client.get("/skills").json() == []

    conflict = client.post(f"/skills/{skill_id}/archive")
    assert conflict.status_code == 409

    restored = client.post(f"/skills/{skill_id}/restore")
    assert restored.status_code == 200
    assert [s["id"] for s in client.get("/skills").json()] == [skill_id]


def test_reorder_persists_the_new_order(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    ids = [
        client.post("/skills", json=build_skill_write(name=name).model_dump()).json()["id"]
        for name in ("A", "B", "C")
    ]
    new_order = [ids[2], ids[0], ids[1]]
    reordered = client.post("/skills/reorder", json={"skill_ids": new_order})
    assert reordered.status_code == 200
    assert [s["id"] for s in reordered.json()] == new_order
    assert [s["id"] for s in client.get("/skills").json()] == new_order


def test_unauthenticated_request_is_rejected(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    client.cookies.clear()
    assert client.get("/skills").status_code == 401


def test_not_found_skill_is_a_404_problem(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    response = client.get("/skills/999")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


def test_internal_boundary_attributes_the_named_agent(make_settings: MakeSettings) -> None:
    client, _, captured = _client(make_settings, internal=True)
    created = client.post(
        "/skills", json=build_skill_write().model_dump(), headers=_INTERNAL_HEADERS
    )
    assert created.status_code == 201
    assert captured[-1].actor.type is ActorType.AGENT
    assert captured[-1].actor.label == "claude"


def test_internal_boundary_rejects_a_missing_token(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=True)
    response = client.post(
        "/skills",
        json=build_skill_write().model_dump(),
        headers={USER_ID_HEADER: "1", ACTOR_HEADER: "claude"},
    )
    assert response.status_code == 401
