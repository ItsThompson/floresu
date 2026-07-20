"""End-to-end contract tests for the /worklog surface on both app shapes.

Drives the real router, service, and write-event seam through ``TestClient`` with
the in-memory repository substituted for Postgres. Asserts the create/read/list/
edit/archive/restore/tags flow and RFC 9457 problem+json errors on the external
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
from floresu.worklog.router import create_worklog_router
from floresu.worklog.service import WorklogService
from tests.worklog_fakes import (
    FakeSession,
    InMemoryWorklogRepository,
    build_worklog_write,
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
) -> tuple[TestClient, InMemoryWorklogRepository, list[WriteEvent]]:
    repo = InMemoryWorklogRepository()
    publisher, captured = capturing_publisher()

    def provider(request: Request) -> WorklogService:
        return WorklogService(cast("AsyncSession", FakeSession()), repo, request.app.state.events)

    if internal:
        router = create_worklog_router(
            provider, identity=require_internal_user, actor=resolve_internal_actor
        )
        settings = make_settings(service="floresu-internal", internal_api_token=_INTERNAL_TOKEN)
    else:
        router = create_worklog_router(provider, identity=require_user, actor=resolve_web_actor)
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


def test_create_read_and_list_an_entry(make_settings: MakeSettings) -> None:
    client, repo, captured = _client(make_settings, internal=False)
    repo.own_source(1, 10)
    created = client.post(
        "/worklog",
        json=build_worklog_write(tags=["api"], source_ids=[10]).model_dump(mode="json"),
    )
    assert created.status_code == 201
    body = created.json()
    assert body["title"] == "Shipped the search API"
    assert body["tags"] == ["api"]
    assert body["source_ids"] == [10]
    assert body["bullet_ids"] == []
    assert body["archived_at"] is None
    worklog_id = body["id"]

    fetched = client.get(f"/worklog/{worklog_id}")
    assert fetched.status_code == 200
    assert fetched.json()["tags"] == ["api"]

    listed = client.get("/worklog")
    assert listed.status_code == 200
    assert [entry["id"] for entry in listed.json()] == [worklog_id]

    assert captured[-1].action.value == "create"
    assert captured[-1].actor.type is ActorType.HUMAN


def test_create_requires_a_title_and_date(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    payload = build_worklog_write().model_dump(mode="json")
    del payload["title"]
    response = client.post("/worklog", json=payload)
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"


def test_attaching_a_foreign_source_is_a_422(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    payload = build_worklog_write(source_ids=[999]).model_dump(mode="json")
    response = client.post("/worklog", json=payload)
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"


def test_archive_removes_from_active_list_and_double_archive_conflicts(
    make_settings: MakeSettings,
) -> None:
    client, _, _ = _client(make_settings, internal=False)
    worklog_id = client.post("/worklog", json=build_worklog_write().model_dump(mode="json")).json()[
        "id"
    ]

    archived = client.post(f"/worklog/{worklog_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert client.get("/worklog").json() == []
    assert client.get(f"/worklog/{worklog_id}").status_code == 200
    assert len(client.get("/worklog", params={"include_archived": True}).json()) == 1

    conflict = client.post(f"/worklog/{worklog_id}/archive")
    assert conflict.status_code == 409
    assert conflict.headers["content-type"] == "application/problem+json"


def test_restore_returns_an_entry_to_the_active_list(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    worklog_id = client.post("/worklog", json=build_worklog_write().model_dump(mode="json")).json()[
        "id"
    ]
    client.post(f"/worklog/{worklog_id}/archive")

    restored = client.post(f"/worklog/{worklog_id}/restore")
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
    assert [entry["id"] for entry in client.get("/worklog").json()] == [worklog_id]


def test_edit_updates_tags_and_content(make_settings: MakeSettings) -> None:
    client, _, captured = _client(make_settings, internal=False)
    worklog_id = client.post(
        "/worklog", json=build_worklog_write(tags=["api"]).model_dump(mode="json")
    ).json()["id"]

    edited = client.put(
        f"/worklog/{worklog_id}",
        json=build_worklog_write(title="Revised title", tags=["api", "python"]).model_dump(
            mode="json"
        ),
    )
    assert edited.status_code == 200
    assert edited.json()["title"] == "Revised title"
    assert edited.json()["tags"] == ["api", "python"]
    assert captured[-1].action.value == "update"


def test_list_tags_returns_the_reuse_set(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    client.post(
        "/worklog", json=build_worklog_write(tags=["python", "api"]).model_dump(mode="json")
    )
    client.post("/worklog", json=build_worklog_write(tags=["api"]).model_dump(mode="json"))

    tags = client.get("/worklog/tags")
    assert tags.status_code == 200
    assert [tag["label"] for tag in tags.json()] == ["api", "python"]


def test_unauthenticated_request_is_rejected(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    client.cookies.clear()
    assert client.get("/worklog").status_code == 401


def test_not_found_entry_is_a_404_problem(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    response = client.get("/worklog/999")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


def test_internal_boundary_attributes_the_named_agent(make_settings: MakeSettings) -> None:
    client, _, captured = _client(make_settings, internal=True)
    created = client.post(
        "/worklog",
        json=build_worklog_write().model_dump(mode="json"),
        headers=_INTERNAL_HEADERS,
    )
    assert created.status_code == 201
    assert captured[-1].actor.type is ActorType.AGENT
    assert captured[-1].actor.label == "claude"


def test_internal_boundary_rejects_a_missing_token(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=True)
    response = client.post(
        "/worklog",
        json=build_worklog_write().model_dump(mode="json"),
        headers={USER_ID_HEADER: "1", ACTOR_HEADER: "claude"},
    )
    assert response.status_code == 401
