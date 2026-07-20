"""Identity resolution at the external boundary: require_user + inbound strip."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from floresu.accounts.session import create_session_verifier
from floresu.accounts.tokens import SessionTokenCodec
from floresu.core.errors import build_exception_handlers
from floresu.core.identity import (
    SESSION_COOKIE_NAME,
    USER_ID_HEADER,
    StripInboundIdentityMiddleware,
    require_user,
)
from tests.accounts_fakes import build_test_codec


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
