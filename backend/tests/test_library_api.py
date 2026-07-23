"""End-to-end contract tests for the /bullets surface on both app shapes.

Drives the real router, service, and write-event seam through ``TestClient`` with
the in-memory repository substituted for Postgres. Asserts the create/read/list/
edit/archive/restore flow and RFC 9457 problem+json errors on the external
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
from floresu.library.router import create_bullets_router
from floresu.library.service import LibraryService
from tests.library_fakes import (
    InMemoryBulletUsageCounter,
    InMemoryLibraryRepository,
    build_bullet_write,
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
    make_settings: MakeSettings,
    *,
    internal: bool,
    usage: InMemoryBulletUsageCounter | None = None,
) -> tuple[TestClient, InMemoryLibraryRepository, list[WriteEvent]]:
    repo = InMemoryLibraryRepository()
    publisher = CapturingWriteEventPublisher()
    captured = publisher.captured
    counter = usage if usage is not None else InMemoryBulletUsageCounter()

    def provider(request: Request) -> LibraryService:
        return LibraryService(
            cast("AsyncSession", FakeSession()), repo, request.app.state.events, counter
        )

    if internal:
        router = create_bullets_router(
            provider, identity=require_internal_user, actor=resolve_internal_actor
        )
        settings = make_settings(service="floresu-internal", internal_api_token=_INTERNAL_TOKEN)
    else:
        router = create_bullets_router(provider, identity=require_user, actor=resolve_web_actor)
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


def test_create_read_and_list_a_bullet(make_settings: MakeSettings) -> None:
    client, repo, captured = _client(make_settings, internal=False)
    repo.own_source(1, 100)
    repo.own_worklog(1, 10)
    created = client.post(
        "/bullets",
        json=build_bullet_write(source_ids=[100], worklog_ids=[10]).model_dump(mode="json"),
    )
    assert created.status_code == 201
    body = created.json()
    assert body["source_ids"] == [100]
    assert body["worklog_ids"] == [10]
    assert body["used_in_count"] == 0
    assert body["revision"] == 1
    assert body["archived_at"] is None
    bullet_id = body["id"]

    fetched = client.get(f"/bullets/{bullet_id}")
    assert fetched.status_code == 200
    assert fetched.json()["worklog_ids"] == [10]

    listed = client.get("/bullets")
    assert listed.status_code == 200
    assert [bullet["id"] for bullet in listed.json()] == [bullet_id]

    assert captured[-1].action.value == "create"
    assert captured[-1].actor.type is ActorType.HUMAN


def test_create_requires_text(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    payload = build_bullet_write().model_dump(mode="json")
    del payload["text"]
    response = client.post("/bullets", json=payload)
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"


def test_list_carries_the_real_used_in_count_on_the_wire(make_settings: MakeSettings) -> None:
    counter = InMemoryBulletUsageCounter()
    client, _, _ = _client(make_settings, internal=False, usage=counter)
    bullet_id = client.post("/bullets", json=build_bullet_write().model_dump(mode="json")).json()[
        "id"
    ]
    counter.set_count(bullet_id, 2)
    listed = client.get("/bullets").json()
    assert [bullet["used_in_count"] for bullet in listed] == [2]
    assert client.get(f"/bullets/{bullet_id}").json()["used_in_count"] == 2


def test_framing_a_foreign_source_is_a_422(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    payload = build_bullet_write(source_ids=[999]).model_dump(mode="json")
    response = client.post("/bullets", json=payload)
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"


def test_archive_removes_from_active_list_and_double_archive_conflicts(
    make_settings: MakeSettings,
) -> None:
    client, _, _ = _client(make_settings, internal=False)
    bullet_id = client.post("/bullets", json=build_bullet_write().model_dump(mode="json")).json()[
        "id"
    ]

    archived = client.post(f"/bullets/{bullet_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert client.get("/bullets").json() == []
    assert client.get(f"/bullets/{bullet_id}").status_code == 200
    assert len(client.get("/bullets", params={"include_archived": True}).json()) == 1

    conflict = client.post(f"/bullets/{bullet_id}/archive")
    assert conflict.status_code == 409
    assert conflict.headers["content-type"] == "application/problem+json"


def test_restore_returns_a_bullet_to_the_active_list(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    bullet_id = client.post("/bullets", json=build_bullet_write().model_dump(mode="json")).json()[
        "id"
    ]
    client.post(f"/bullets/{bullet_id}/archive")

    restored = client.post(f"/bullets/{bullet_id}/restore")
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
    assert [bullet["id"] for bullet in client.get("/bullets").json()] == [bullet_id]


def test_edit_updates_text_and_edges(make_settings: MakeSettings) -> None:
    client, repo, captured = _client(make_settings, internal=False)
    repo.own_worklog(1, 10)
    created = client.post("/bullets", json=build_bullet_write().model_dump(mode="json")).json()
    bullet_id = created["id"]

    edited = client.put(
        f"/bullets/{bullet_id}",
        json=build_bullet_write(text="Reworded framing.", worklog_ids=[10]).model_dump(mode="json"),
        headers={"If-Match": str(created["revision"])},
    )
    assert edited.status_code == 200
    assert edited.json()["text"] == "Reworded framing."
    assert edited.json()["worklog_ids"] == [10]
    # The CAS advanced the optimistic token by one.
    assert edited.json()["revision"] == created["revision"] + 1
    assert captured[-1].action.value == "update"


def test_put_without_if_match_is_a_422(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    bullet_id = client.post("/bullets", json=build_bullet_write().model_dump(mode="json")).json()[
        "id"
    ]
    # A missing If-Match must not fall through to an unguarded write: it is a 4xx.
    response = client.put(
        f"/bullets/{bullet_id}",
        json=build_bullet_write(text="No guard.").model_dump(mode="json"),
    )
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"


def test_put_with_a_stale_if_match_is_a_409(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    created = client.post("/bullets", json=build_bullet_write().model_dump(mode="json")).json()
    bullet_id = created["id"]
    # First edit advances the token past the loaded revision.
    ok = client.put(
        f"/bullets/{bullet_id}",
        json=build_bullet_write(text="First.").model_dump(mode="json"),
        headers={"If-Match": str(created["revision"])},
    )
    assert ok.status_code == 200
    # A second edit carrying the now-stale original revision is a recoverable 409.
    stale = client.put(
        f"/bullets/{bullet_id}",
        json=build_bullet_write(text="Stale.").model_dump(mode="json"),
        headers={"If-Match": str(created["revision"])},
    )
    assert stale.status_code == 409
    assert stale.headers["content-type"] == "application/problem+json"


def test_unauthenticated_request_is_rejected(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    client.cookies.clear()
    assert client.get("/bullets").status_code == 401


def test_not_found_bullet_is_a_404_problem(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    response = client.get("/bullets/999")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


def test_internal_boundary_attributes_the_named_agent(make_settings: MakeSettings) -> None:
    client, _, captured = _client(make_settings, internal=True)
    created = client.post(
        "/bullets",
        json=build_bullet_write().model_dump(mode="json"),
        headers=_INTERNAL_HEADERS,
    )
    assert created.status_code == 201
    assert captured[-1].actor.type is ActorType.AGENT
    assert captured[-1].actor.label == "claude"


def test_internal_boundary_rejects_a_missing_token(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=True)
    response = client.post(
        "/bullets",
        json=build_bullet_write().model_dump(mode="json"),
        headers={USER_ID_HEADER: "1", ACTOR_HEADER: "claude"},
    )
    assert response.status_code == 401
