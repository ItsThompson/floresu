"""End-to-end contract tests for the /auth + /me surface on an external-shaped app.

Asserts RFC 9457 problem+json error shapes, HTTP-only session-cookie attributes,
that require_user resolves the cookie to the right user with any spoofed
X-User-ID stripped, and the register/login/refresh/logout/revocation flow. The
service is backed by the in-memory repository; no database is required.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
from fastapi.testclient import TestClient

from floresu.accounts.api import create_accounts_router
from floresu.accounts.config import REFRESH_COOKIE_NAME, CookieConfig
from floresu.accounts.me_api import create_me_router
from floresu.accounts.service import AccountService
from floresu.accounts.session import create_session_verifier
from floresu.core.app_factory import create_app
from floresu.core.errors import build_exception_handlers
from floresu.core.headers import USER_ID_HEADER
from floresu.core.identity import (
    SESSION_COOKIE_NAME,
    StripInboundIdentityMiddleware,
    require_user,
)
from floresu.core.settings import AppSettings
from tests.accounts_fakes import (
    InMemoryAccountRepository,
    build_test_codec,
    build_test_hasher,
)

MakeSettings = Callable[..., AppSettings]

_PASSWORD = "Str0ngPass"
_DEV_COOKIES = CookieConfig(secure=False, domain=None)


def _build_client(make_settings: MakeSettings) -> tuple[TestClient, InMemoryAccountRepository]:
    repo = InMemoryAccountRepository()
    codec = build_test_codec()
    hasher = build_test_hasher()

    def provider() -> AccountService:
        return AccountService(repo, hasher, codec)

    async def is_revoked(sid: str) -> bool:
        return await repo.is_session_revoked(sid)

    app = create_app(
        make_settings(service="floresu-external", environment="development"),
        routers=[
            create_accounts_router(provider, cookie_config=_DEV_COOKIES),
            create_me_router(provider, identity=require_user),
        ],
        exception_handlers=build_exception_handlers(),
    )
    app.state.session_verifier = create_session_verifier(codec, is_revoked)
    app.add_middleware(StripInboundIdentityMiddleware)
    return TestClient(app), repo


def _set_cookie_headers(response: httpx.Response) -> list[str]:
    return response.headers.get_list("set-cookie")


def test_register_sets_httponly_cookies_and_returns_the_user(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.post(
        "/auth/register", json={"email": "Ada@Example.com", "password": _PASSWORD}
    )
    assert response.status_code == 201
    body = response.json()
    # Email normalized; the password hash never crosses the wire.
    assert body["email"] == "ada@example.com"
    assert body["has_completed_onboarding"] is False
    assert "password_hash" not in body and "password" not in body

    cookies = " ".join(_set_cookie_headers(response)).lower()
    assert SESSION_COOKIE_NAME in cookies
    assert REFRESH_COOKIE_NAME in cookies
    # Not readable by JS.
    assert "httponly" in cookies


def test_register_then_me_returns_the_same_user(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    registered = client.post(
        "/auth/register", json={"email": "ada@example.com", "password": _PASSWORD}
    ).json()
    me = client.get("/me")
    assert me.status_code == 200
    assert me.json()["id"] == registered["id"]
    assert me.json()["email"] == "ada@example.com"


def test_complete_onboarding_persists_and_survives_refresh(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    client.post("/auth/register", json={"email": "ada@example.com", "password": _PASSWORD})
    assert client.get("/me").json()["has_completed_onboarding"] is False

    completed = client.post("/me/onboarding")
    assert completed.status_code == 200
    assert completed.json()["has_completed_onboarding"] is True

    # Persisted: a plain re-read and a fresh session (refresh) both see it set, so
    # the wizard never reappears on reload.
    assert client.get("/me").json()["has_completed_onboarding"] is True
    assert client.post("/auth/refresh").json()["has_completed_onboarding"] is True


def test_complete_onboarding_requires_a_session(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    assert client.post("/me/onboarding").status_code == 401


def test_duplicate_email_is_a_409_field_error_and_no_second_account(
    make_settings: MakeSettings,
) -> None:
    client, repo = _build_client(make_settings)
    client.post("/auth/register", json={"email": "ada@example.com", "password": _PASSWORD})
    conflict = client.post(
        "/auth/register", json={"email": "ADA@example.com", "password": _PASSWORD}
    )
    assert conflict.status_code == 409
    assert conflict.headers["content-type"] == "application/problem+json"
    body = conflict.json()
    assert body["code"] == "CONFLICT"
    assert body["fields"]["email"]
    # Exactly one account exists.
    assert len(repo._by_id) == 1


def test_weak_password_is_a_422_field_error(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.post("/auth/register", json={"email": "ada@example.com", "password": "weak"})
    assert response.status_code == 422
    assert response.json()["fields"]["password"]


def test_wrong_password_and_unknown_email_are_the_same_generic_401(
    make_settings: MakeSettings,
) -> None:
    client, _ = _build_client(make_settings)
    client.post("/auth/register", json={"email": "ada@example.com", "password": _PASSWORD})

    wrong = client.post("/auth/login", json={"email": "ada@example.com", "password": "WrongPass9"})
    unknown = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": _PASSWORD}
    )
    assert wrong.status_code == unknown.status_code == 401
    # Identical detail: no account-existence leak.
    assert wrong.json()["detail"] == unknown.json()["detail"]


def test_login_is_case_insensitive_on_email(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    client.post("/auth/register", json={"email": "Ada@Example.com", "password": _PASSWORD})
    # Clear cookies so login is the thing establishing the session.
    client.cookies.clear()
    response = client.post("/auth/login", json={"email": "ada@example.com", "password": _PASSWORD})
    assert response.status_code == 200
    assert client.get("/me").status_code == 200


def test_refresh_rotates_the_session_and_old_refresh_is_rejected(
    make_settings: MakeSettings,
) -> None:
    client, _ = _build_client(make_settings)
    client.post("/auth/register", json={"email": "ada@example.com", "password": _PASSWORD})
    stale_refresh = client.cookies.get(REFRESH_COOKIE_NAME)
    assert stale_refresh is not None

    assert client.post("/auth/refresh").status_code == 200
    assert client.get("/me").status_code == 200

    # Replaying the pre-rotation refresh token is rejected (rotation + revoke).
    client.cookies.set(REFRESH_COOKIE_NAME, stale_refresh, path="/auth")
    assert client.post("/auth/refresh").status_code == 401


def test_logout_clears_cookies_and_protected_routes_then_redirect(
    make_settings: MakeSettings,
) -> None:
    client, _ = _build_client(make_settings)
    client.post("/auth/register", json={"email": "ada@example.com", "password": _PASSWORD})
    assert client.get("/me").status_code == 200

    logout = client.post("/auth/logout")
    assert logout.status_code == 204
    # After logout the session cookie is cleared, so /me is unauthorized.
    assert client.get("/me").status_code == 401


def test_a_logged_out_session_cannot_be_refreshed(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    client.post("/auth/register", json={"email": "ada@example.com", "password": _PASSWORD})
    refresh_before_logout = client.cookies.get(REFRESH_COOKIE_NAME)
    assert refresh_before_logout is not None
    client.post("/auth/logout")

    # The revoked sid cannot mint a new session even with its refresh token.
    client.cookies.set(REFRESH_COOKIE_NAME, refresh_before_logout, path="/auth")
    assert client.post("/auth/refresh").status_code == 401


def test_refresh_without_a_cookie_is_401(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    assert client.post("/auth/refresh").status_code == 401


def test_spoofed_x_user_id_cannot_impersonate(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    # No session, but a spoofed identity header: the strip middleware drops it.
    response = client.get("/me", headers={USER_ID_HEADER: "999"})
    assert response.status_code == 401


def test_cookie_identity_wins_over_a_spoofed_header(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    registered = client.post(
        "/auth/register", json={"email": "ada@example.com", "password": _PASSWORD}
    ).json()
    me = client.get("/me", headers={USER_ID_HEADER: "999"})
    assert me.status_code == 200
    # Resolved from the cookie, never the spoofed header.
    assert me.json()["id"] == registered["id"]
