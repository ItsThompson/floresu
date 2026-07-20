"""The internal-token trust boundary (:func:`require_internal_user`).

Builds a probe app from the shared factory wired like the internal app
(problem+json handlers, an injected internal token) and mounts a route that uses
the dependency, then drives it through the real ASGI stack via ``TestClient``:
the token is verified (constant-time, fail-closed) and only then is ``X-User-ID``
trusted. Also asserts the real internal app mounts no web-only route and that the
agent bearer is never consulted at this seam.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from floresu.api_internal.main import app as internal_app
from floresu.core.app_factory import create_app
from floresu.core.errors import build_exception_handlers
from floresu.core.headers import INTERNAL_API_TOKEN_HEADER, USER_ID_HEADER
from floresu.core.identity import _token_is_valid, require_internal_user
from floresu.core.route_registry import mounted_product_routes
from floresu.core.settings import INTERNAL_PORT, INTERNAL_SERVICE, AppSettings

INTERNAL_TOKEN = "test-internal-token"
USER = "42"

MakeSettings = Callable[..., AppSettings]


def _internal_app(make_settings: MakeSettings, *, token: str = INTERNAL_TOKEN) -> FastAPI:
    router = APIRouter()

    @router.get("/probe/user")
    async def probe_user(user_id: str = Depends(require_internal_user)) -> dict[str, str]:
        return {"user_id": user_id}

    return create_app(
        make_settings(service=INTERNAL_SERVICE, port=INTERNAL_PORT, internal_api_token=token),
        routers=[router],
        exception_handlers=build_exception_handlers(),
    )


@pytest.fixture
def client(make_settings: MakeSettings) -> TestClient:
    return TestClient(_internal_app(make_settings))


def test_rejects_when_token_header_is_absent(client: TestClient) -> None:
    response = client.get("/probe/user", headers={USER_ID_HEADER: USER})
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_rejects_a_wrong_token(client: TestClient) -> None:
    response = client.get(
        "/probe/user",
        headers={INTERNAL_API_TOKEN_HEADER: "wrong", USER_ID_HEADER: USER},
    )
    assert response.status_code == 401


def test_fails_closed_when_the_server_has_no_token_configured(make_settings: MakeSettings) -> None:
    # Even a caller presenting a token is denied when the server token is unset.
    unconfigured = TestClient(_internal_app(make_settings, token=""))
    response = unconfigured.get(
        "/probe/user",
        headers={INTERNAL_API_TOKEN_HEADER: "anything", USER_ID_HEADER: USER},
    )
    assert response.status_code == 401


def test_accepts_a_valid_token_and_returns_the_trusted_user_id(client: TestClient) -> None:
    response = client.get(
        "/probe/user",
        headers={INTERNAL_API_TOKEN_HEADER: INTERNAL_TOKEN, USER_ID_HEADER: USER},
    )
    assert response.status_code == 200
    assert response.json() == {"user_id": USER}


def test_rejects_a_valid_token_with_no_user_identity(client: TestClient) -> None:
    response = client.get("/probe/user", headers={INTERNAL_API_TOKEN_HEADER: INTERNAL_TOKEN})
    assert response.status_code == 401


def test_the_agent_bearer_is_never_trusted_at_the_boundary(client: TestClient) -> None:
    # A bearer grants nothing here: without the internal token the request is
    # denied, and with it no bearer is needed. The MCP client is responsible for
    # not forwarding the bearer past the boundary (verified in its own package).
    only_bearer = client.get(
        "/probe/user",
        headers={"Authorization": "Bearer forged", USER_ID_HEADER: USER},
    )
    assert only_bearer.status_code == 401

    no_bearer = client.get(
        "/probe/user",
        headers={INTERNAL_API_TOKEN_HEADER: INTERNAL_TOKEN, USER_ID_HEADER: USER},
    )
    assert no_bearer.status_code == 200


def test_token_predicate_denies_when_unconfigured() -> None:
    assert _token_is_valid("", "anything") is False


def test_token_predicate_matches_only_the_exact_token() -> None:
    assert _token_is_valid("s3cret", "s3cret") is True
    # A same-length token differing at the first or last byte is rejected; the
    # comparison uses hmac.compare_digest, which does not short-circuit on the
    # first differing byte.
    assert _token_is_valid("s3cret", "X3cret") is False
    assert _token_is_valid("s3cret", "s3creX") is False
    assert _token_is_valid("s3cret", "s3cre") is False


def test_internal_app_mounts_no_permanent_delete_route() -> None:
    # Permanent delete is web-human-only; agents get no delete route on :8001.
    delete_routes = [key for key in mounted_product_routes(internal_app) if key.method == "DELETE"]
    assert delete_routes == []
