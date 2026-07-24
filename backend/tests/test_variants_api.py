"""End-to-end contract tests for the /identity-variants surface on both app shapes.

Drives the real router, service, and write-event seam through ``TestClient`` with
the in-memory repository substituted for Postgres. Asserts the create/read/list/
update/archive flow, the default-flip and archive gates, the replacement-required
signal, and RFC 9457 problem+json errors on the external (cookie) boundary, plus
that the internal (trusted-header) boundary resolves the named-agent actor. It also
asserts the router exposes no reorder route (variants are unordered per the profile
family table). No database is required.
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
from floresu.profile.variants.config import REPLACEMENT_REQUIRED_RULE
from floresu.profile.variants.router import VARIANTS_PATH, create_variants_router
from floresu.profile.variants.service import IdentityVariantService
from floresu.profile.variants.wiring import build_variant_service_provider
from tests.support.fakes import CapturingWriteEventPublisher, FakeSession
from tests.variants_fakes import (
    InMemoryIdentityVariantRepository,
    build_variant_write,
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
) -> tuple[TestClient, InMemoryIdentityVariantRepository, list[WriteEvent]]:
    repo = InMemoryIdentityVariantRepository()
    publisher = CapturingWriteEventPublisher()
    captured = publisher.captured

    def provider(request: Request) -> IdentityVariantService:
        return IdentityVariantService(
            cast("AsyncSession", FakeSession()), repo, request.app.state.events
        )

    if internal:
        router = create_variants_router(
            provider, identity=require_internal_user, actor=resolve_internal_actor
        )
        settings = make_settings(service="floresu-internal", internal_api_token=_INTERNAL_TOKEN)
    else:
        router = create_variants_router(provider, identity=require_user, actor=resolve_web_actor)
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


def test_create_first_variant_is_default_and_serializes_contact(
    make_settings: MakeSettings,
) -> None:
    client, _, captured = _client(make_settings, internal=False)
    created = client.post(
        "/identity-variants", json=build_variant_write(is_default=False).model_dump()
    )
    assert created.status_code == 201
    body = created.json()
    assert body["label"] == "Personal"
    assert body["is_default"] is True  # first variant forced default
    assert body["contact"]["email"] == "ada@example.com"
    assert body["contact"]["phone"] is None
    assert body["links"][0]["url"] == "https://ada.example.com"

    assert captured[-1].action.value == "create"
    assert captured[-1].actor.type is ActorType.HUMAN


def test_marking_a_variant_default_flips_the_previous(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    first = client.post(
        "/identity-variants", json=build_variant_write(label="Personal").model_dump()
    ).json()
    second = client.post(
        "/identity-variants", json=build_variant_write(label="Academic").model_dump()
    ).json()
    assert second["is_default"] is False

    promoted = client.put(
        f"/identity-variants/{second['id']}",
        json=build_variant_write(label="Academic", is_default=True).model_dump(),
    )
    assert promoted.status_code == 200
    assert promoted.json()["is_default"] is True
    assert client.get(f"/identity-variants/{first['id']}").json()["is_default"] is False


def test_default_archive_is_blocked_then_allowed_after_promotion(
    make_settings: MakeSettings,
) -> None:
    client, _, _ = _client(make_settings, internal=False)
    first = client.post(
        "/identity-variants", json=build_variant_write(label="Personal").model_dump()
    ).json()
    second = client.post(
        "/identity-variants", json=build_variant_write(label="Academic").model_dump()
    ).json()

    blocked = client.post(f"/identity-variants/{first['id']}/archive")
    assert blocked.status_code == 409
    assert blocked.headers["content-type"] == "application/problem+json"

    client.put(
        f"/identity-variants/{second['id']}",
        json=build_variant_write(label="Academic", is_default=True).model_dump(),
    )
    allowed = client.post(f"/identity-variants/{first['id']}/archive")
    assert allowed.status_code == 200
    assert allowed.json()["archived_at"] is not None


def test_archiving_a_referenced_variant_surfaces_the_signal(make_settings: MakeSettings) -> None:
    client, repo, _ = _client(make_settings, internal=False)
    client.post("/identity-variants", json=build_variant_write(label="Personal").model_dump())
    second = client.post(
        "/identity-variants", json=build_variant_write(label="Academic").model_dump()
    ).json()
    repo.set_references(1, second["id"], [7])

    response = client.post(f"/identity-variants/{second['id']}/archive")
    assert response.status_code == 422
    body = response.json()
    assert body["violations"][0]["rule"] == REPLACEMENT_REQUIRED_RULE
    assert body["violations"][0]["ids"] == ["7"]


def test_duplicate_label_is_a_409(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    client.post("/identity-variants", json=build_variant_write(label="Personal").model_dump())
    conflict = client.post(
        "/identity-variants", json=build_variant_write(label="Personal").model_dump()
    )
    assert conflict.status_code == 409


def test_list_and_restore_flow(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    client.post("/identity-variants", json=build_variant_write(label="Personal").model_dump())
    second = client.post(
        "/identity-variants", json=build_variant_write(label="Academic").model_dump()
    ).json()

    listed = client.get("/identity-variants")
    assert listed.status_code == 200
    assert {v["label"] for v in listed.json()} == {"Personal", "Academic"}

    client.post(f"/identity-variants/{second['id']}/archive")
    restored = client.post(f"/identity-variants/{second['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None


def test_the_router_exposes_no_reorder_route(make_settings: MakeSettings) -> None:
    # Identity variants are unordered: the profile family table marks reorder valid
    # for sources and skills but not identity_variant, so the router must not mount
    # a reorder path.
    router = create_variants_router(
        build_variant_service_provider(), identity=require_user, actor=resolve_web_actor
    )
    reorder_path = f"{VARIANTS_PATH}/reorder"
    assert all(getattr(route, "path", None) != reorder_path for route in router.routes)


def test_unauthenticated_request_is_rejected(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    client.cookies.clear()
    assert client.get("/identity-variants").status_code == 401


def test_not_found_variant_is_a_404_problem(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=False)
    response = client.get("/identity-variants/999")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


def test_internal_boundary_attributes_the_named_agent(make_settings: MakeSettings) -> None:
    client, _, captured = _client(make_settings, internal=True)
    created = client.post(
        "/identity-variants", json=build_variant_write().model_dump(), headers=_INTERNAL_HEADERS
    )
    assert created.status_code == 201
    assert captured[-1].actor.type is ActorType.AGENT
    assert captured[-1].actor.label == "claude"


def test_internal_boundary_rejects_a_missing_token(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings, internal=True)
    response = client.post(
        "/identity-variants",
        json=build_variant_write().model_dump(),
        headers={USER_ID_HEADER: "1", ACTOR_HEADER: "claude"},
    )
    assert response.status_code == 401
