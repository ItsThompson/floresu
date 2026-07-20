"""The actor descriptor and its resolution at each trust boundary.

The web resolver and the pure model are covered directly; the internal resolver
is driven through the real ASGI stack because it resolves an agent actor only
behind a validated internal token.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from floresu.core.actor import Actor, ActorType, resolve_internal_actor, resolve_web_actor
from floresu.core.app_factory import create_app
from floresu.core.errors import build_exception_handlers
from floresu.core.headers import ACTOR_HEADER, INTERNAL_API_TOKEN_HEADER, USER_ID_HEADER
from floresu.core.settings import INTERNAL_PORT, INTERNAL_SERVICE, AppSettings

INTERNAL_TOKEN = "test-internal-token"
USER = "42"

MakeSettings = Callable[..., AppSettings]


# --- the pure descriptor and the web boundary ---


def test_web_boundary_resolves_a_human_actor_with_no_label() -> None:
    actor = resolve_web_actor()
    assert actor.type is ActorType.HUMAN
    assert actor.label is None


def test_actor_defaults_to_no_label() -> None:
    assert Actor(type=ActorType.HUMAN).label is None


def test_actor_is_frozen() -> None:
    actor = Actor(type=ActorType.AGENT, label="claude")
    with pytest.raises(ValidationError):
        actor.label = "gemini"


def test_actor_serializes_to_the_wire_shape() -> None:
    # Serializable into the audit row (actor_type/actor_label) and the SSE frame.
    assert resolve_web_actor().model_dump(mode="json") == {"type": "human", "label": None}
    assert Actor(type=ActorType.AGENT, label="claude").model_dump(mode="json") == {
        "type": "agent",
        "label": "claude",
    }


# --- the internal boundary: agent provenance behind the validated token ---


def _actor_client(make_settings: MakeSettings) -> TestClient:
    router = APIRouter()

    @router.get("/probe/actor")
    async def probe_actor(actor: Actor = Depends(resolve_internal_actor)) -> Actor:
        return actor

    app: FastAPI = create_app(
        make_settings(
            service=INTERNAL_SERVICE, port=INTERNAL_PORT, internal_api_token=INTERNAL_TOKEN
        ),
        routers=[router],
        exception_handlers=build_exception_handlers(),
    )
    return TestClient(app)


@pytest.fixture
def client(make_settings: MakeSettings) -> TestClient:
    return _actor_client(make_settings)


def test_resolves_the_named_agent_actor_from_the_actor_header(client: TestClient) -> None:
    response = client.get(
        "/probe/actor",
        headers={
            INTERNAL_API_TOKEN_HEADER: INTERNAL_TOKEN,
            USER_ID_HEADER: USER,
            ACTOR_HEADER: "claude",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"type": "agent", "label": "claude"}


def test_agent_actor_has_no_label_when_the_actor_header_is_absent(client: TestClient) -> None:
    response = client.get(
        "/probe/actor",
        headers={INTERNAL_API_TOKEN_HEADER: INTERNAL_TOKEN, USER_ID_HEADER: USER},
    )
    assert response.status_code == 200
    assert response.json() == {"type": "agent", "label": None}


def test_actor_resolution_is_gated_by_the_internal_token(client: TestClient) -> None:
    # No agent actor can be forged from untrusted headers: an invalid token is
    # rejected before the actor resolves.
    response = client.get("/probe/actor", headers={ACTOR_HEADER: "claude", USER_ID_HEADER: USER})
    assert response.status_code == 401
