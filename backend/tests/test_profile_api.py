"""End-to-end contract tests for the /sources surface on both app shapes.

Drives the real router, service, and write-event seam through ``TestClient`` with
the in-memory repository substituted for Postgres. Asserts the create/read/list/
edit/archive/reorder flow and RFC 9457 problem+json errors on the external
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
from floresu.profile.router import create_sources_router
from floresu.profile.service import SourceService
from tests.profile_fakes import (
    FakeSession,
    InMemorySourceRepository,
    build_project_write,
    build_role_write,
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
) -> tuple[TestClient, InMemorySourceRepository, list[WriteEvent]]:
    repo = InMemorySourceRepository()
    publisher, captured = capturing_publisher()

    def provider(request: Request) -> SourceService:
        return SourceService(cast("AsyncSession", FakeSession()), repo, request.app.state.events)

    if internal:
        router = create_sources_router(
            provider, identity=require_internal_user, actor=resolve_internal_actor
        )
        settings = make_settings(service="floresu-internal", internal_api_token=_INTERNAL_TOKEN)
    else:
        router = create_sources_router(provider, identity=require_user, actor=resolve_web_actor)
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


def test_create_read_and_list_a_role(make_settings: MakeSettings) -> None:
    client, _, captured = _client(make_settings, internal=False)
    created = client.post("/sources", json=build_role_write().model_dump(mode="json"))
    assert created.status_code == 201
    body = created.json()
    assert body["kind"] == "role"
    assert body["detail"]["company"] == "Acme"
    assert body["detail"]["job_title"] == "Senior Engineer"
    assert body["sort_order"] == 0
    assert body["archived_at"] is None
    source_id = body["id"]

    fetched = client.get(f"/sources/{source_id}")
    assert fetched.status_code == 200
    assert fetched.json()["detail"]["company"] == "Acme"

    listed = client.get("/sources")
    assert listed.status_code == 200
    assert [s["id"] for s in listed.json()] == [source_id]
    # The list projection carries no subtype detail.
    assert "detail" not in listed.json()[0]

    # The create flowed through the seam attributed to the human.
    assert captured[-1].action.value == "create"
    assert captured[-1].actor.type is ActorType.HUMAN


def test_open_ended_role_serializes_null_date_end(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    body = client.post(
        "/sources", json=build_role_write(date_end=None).model_dump(mode="json")
    ).json()
    assert body["date_end"] is None


def test_missing_required_field_is_a_422(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    payload = build_role_write().model_dump(mode="json")
    del payload["company"]
    response = client.post("/sources", json=payload)
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"


def test_fields_that_disagree_with_kind_are_rejected(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    payload = build_project_write().model_dump(mode="json")
    payload["company"] = "Acme"  # a role-only field on a project body
    response = client.post("/sources", json=payload)
    assert response.status_code == 422


def test_archive_removes_from_active_list_and_double_archive_conflicts(
    make_settings: MakeSettings,
) -> None:
    client, _, _ = _client(make_settings, internal=False)
    source_id = client.post("/sources", json=build_role_write().model_dump(mode="json")).json()[
        "id"
    ]

    archived = client.post(f"/sources/{source_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert client.get("/sources").json() == []
    # Still directly fetchable, and included when archived are requested.
    assert client.get(f"/sources/{source_id}").status_code == 200
    assert len(client.get("/sources", params={"include_archived": True}).json()) == 1

    conflict = client.post(f"/sources/{source_id}/archive")
    assert conflict.status_code == 409
    assert conflict.headers["content-type"] == "application/problem+json"


def test_restore_returns_a_source_to_the_active_list(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    source_id = client.post("/sources", json=build_role_write().model_dump(mode="json")).json()[
        "id"
    ]
    client.post(f"/sources/{source_id}/archive")

    restored = client.post(f"/sources/{source_id}/restore")
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
    assert [s["id"] for s in client.get("/sources").json()] == [source_id]


def test_update_edits_fields_and_kind_change_is_rejected(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    source_id = client.post("/sources", json=build_role_write().model_dump(mode="json")).json()[
        "id"
    ]

    edited = client.put(
        f"/sources/{source_id}",
        json=build_role_write(job_title="Staff Engineer").model_dump(mode="json"),
    )
    assert edited.status_code == 200
    assert edited.json()["detail"]["job_title"] == "Staff Engineer"

    # Changing kind on update is rejected.
    changed_kind = client.put(
        f"/sources/{source_id}", json=build_project_write().model_dump(mode="json")
    )
    assert changed_kind.status_code == 422


def test_reorder_persists_the_new_order(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    ids = []
    for label in ("A", "B", "C"):
        body = build_role_write(display_label=label).model_dump(mode="json")
        ids.append(client.post("/sources", json=body).json()["id"])
    new_order = [ids[2], ids[0], ids[1]]
    reordered = client.post("/sources/reorder", json={"kind": "role", "source_ids": new_order})
    assert reordered.status_code == 200
    assert [s["id"] for s in reordered.json()] == new_order
    assert [s["id"] for s in client.get("/sources", params={"kind": "role"}).json()] == new_order


def test_unauthenticated_request_is_rejected(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    client.cookies.clear()
    assert client.get("/sources").status_code == 401


def test_not_found_source_is_a_404_problem(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    response = client.get("/sources/999")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


def test_internal_boundary_attributes_the_named_agent(make_settings: MakeSettings) -> None:
    client, _, captured = _client(make_settings, internal=True)
    created = client.post(
        "/sources",
        json=build_role_write().model_dump(mode="json"),
        headers=_INTERNAL_HEADERS,
    )
    assert created.status_code == 201
    # The write is attributed to the named agent from the validated headers.
    assert captured[-1].actor.type is ActorType.AGENT
    assert captured[-1].actor.label == "claude"


def test_internal_boundary_rejects_a_missing_token(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=True)
    # No X-Internal-Api-Token: the trusted-header boundary fails closed.
    response = client.post(
        "/sources",
        json=build_role_write().model_dump(mode="json"),
        headers={USER_ID_HEADER: "1", ACTOR_HEADER: "claude"},
    )
    assert response.status_code == 401
