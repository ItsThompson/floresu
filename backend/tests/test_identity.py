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
from starlette.requests import Request

from floresu.accounts.session import create_session_verifier
from floresu.accounts.tokens import SessionTokenCodec
from floresu.api_internal.main import app as internal_app
from floresu.core.app_factory import create_app
from floresu.core.errors import build_exception_handlers
from floresu.core.headers import INTERNAL_API_TOKEN_HEADER, USER_ID_HEADER
from floresu.core.identity import (
    SESSION_COOKIE_NAME,
    StripInboundIdentityMiddleware,
    _token_is_valid,
    require_internal_user,
    require_user,
)
from floresu.core.route_registry import mounted_product_routes
from floresu.core.settings import INTERNAL_PORT, INTERNAL_SERVICE, AppSettings
from tests.accounts_fakes import build_test_codec

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


def _build_app(
    *, verifier_revoked: set[str] | None = None, wire_verifier: bool = True
) -> tuple[FastAPI, SessionTokenCodec]:
    codec = build_test_codec()
    revoked = verifier_revoked if verifier_revoked is not None else set()

    async def is_revoked(sid: str) -> bool:
        return sid in revoked

    app = FastAPI()
    for key, handler in build_exception_handlers().items():
        app.add_exception_handler(key, handler)

    @app.get("/whoami")
    async def whoami(user_id: str = Depends(require_user)) -> dict[str, str]:
        return {"user_id": user_id}

    @app.get("/echo-header")
    async def echo_header(request: Request) -> dict[str, str | None]:
        # After the strip middleware, a client-supplied X-User-ID must be gone.
        return {"seen": request.headers.get(USER_ID_HEADER)}

    app.add_middleware(StripInboundIdentityMiddleware)
    if wire_verifier:
        app.state.session_verifier = create_session_verifier(codec, is_revoked)
    return app, codec


def test_missing_cookie_is_unauthorized() -> None:
    app, _ = _build_app()
    response = TestClient(app).get("/whoami")
    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"


def test_unwired_verifier_fails_safe_deny() -> None:
    # With no session_verifier on app.state the boundary denies rather than raising.
    app, codec = _build_app(wire_verifier=False)
    cookie = codec.mint_pair("42").access_token
    response = TestClient(app).get("/whoami", cookies={SESSION_COOKIE_NAME: cookie})
    assert response.status_code == 401


def test_valid_cookie_resolves_the_user() -> None:
    app, codec = _build_app()
    cookie = codec.mint_pair("42").access_token
    response = TestClient(app).get("/whoami", cookies={SESSION_COOKIE_NAME: cookie})
    assert response.status_code == 200
    assert response.json() == {"user_id": "42"}


def test_a_revoked_session_cookie_is_unauthorized() -> None:
    revoked: set[str] = set()
    app, codec = _build_app(verifier_revoked=revoked)
    pair = codec.mint_pair("42")
    # The unexpired access cookie resolves until its sid is blacklisted.
    client = TestClient(app)
    ok = client.get("/whoami", cookies={SESSION_COOKIE_NAME: pair.access_token})
    assert ok.status_code == 200
    revoked.add(pair.sid)
    denied = client.get("/whoami", cookies={SESSION_COOKIE_NAME: pair.access_token})
    assert denied.status_code == 401


def test_inbound_x_user_id_is_stripped() -> None:
    app, _ = _build_app()
    response = TestClient(app).get("/echo-header", headers={USER_ID_HEADER: "999"})
    assert response.json() == {"seen": None}


def test_spoofed_x_user_id_cannot_impersonate() -> None:
    # A client sends X-User-ID but no valid cookie: it must not authenticate.
    app, _ = _build_app()
    response = TestClient(app).get("/whoami", headers={USER_ID_HEADER: "999"})
    assert response.status_code == 401


def test_cookie_wins_over_a_spoofed_header() -> None:
    # Even with a spoofed X-User-ID, the resolved identity is the cookie's user.
    app, codec = _build_app()
    cookie = codec.mint_pair("42").access_token
    response = TestClient(app).get(
        "/whoami",
        cookies={SESSION_COOKIE_NAME: cookie},
        headers={USER_ID_HEADER: "999"},
    )
    assert response.json() == {"user_id": "42"}
