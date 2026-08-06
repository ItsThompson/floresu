"""App-assembly tests: PRM, health/readiness, metrics, and the 401 boundary.

Boots the real RS app (:func:`create_rs_app`) with an injected key provider
(faked JWKS), internal client, and rate limiter, and asserts the acceptance
surface end to end: PRM served from pinned config, /readyz gated on JWKS
reachability, /metrics exposed, an unauthenticated tool call rejected with 401 +
WWW-Authenticate pointing at the PRM, and both /mcp and /mcp/ served without a
307 redirect.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr

from floresu_mcp.app import build_app, create_rs_app
from floresu_mcp.client import InternalApiClient
from floresu_mcp.config import MCP_PATH, PRM_PATH
from floresu_mcp.keys import RemoteKeyProvider
from floresu_mcp.ratelimit import RateLimiter
from floresu_mcp.settings import build_rs_settings
from floresu_mcp.state import get_rs_deps
from tests.conftest import MakeSettings
from tests.fakes import InMemoryRateLimitStore
from tests.mcp_harness import AgentHarness
from tests.token_factory import ISSUER, RESOURCE, make_fetch, mint, new_key, public_jwks

if TYPE_CHECKING:
    from joserfc.jwk import KeySet

    from floresu_mcp.keys import KeyProvider

_MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
_TOOLS_LIST = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
# A representative sample of the registered surface: one read tool and one write
# tool. The full read/write surfaces are asserted in the per-domain tool tests, so
# this app-assembly check only needs the tool transport to serve a non-empty,
# superset-containing list.
_REPRESENTATIVE_TOOLS = {"worklog_query", "worklog_create"}


class _FailingKeyProvider:
    """A key provider whose discovery always fails (AS unreachable)."""

    async def key_set_for(self, kid: str | None) -> KeySet:
        raise RuntimeError("AS unreachable")

    async def load(self) -> KeySet:
        raise RuntimeError("AS unreachable")


def _internal_client() -> InternalApiClient:
    http = httpx.AsyncClient(
        base_url="http://backend:8001",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=[])),
    )
    return InternalApiClient(http, api_token=SecretStr("tok"))


def _limiter() -> RateLimiter:
    return RateLimiter(
        InMemoryRateLimitStore(), window_seconds=60, request_budget=120, embed_write_budget=30
    )


def _build(
    make_settings: MakeSettings,
    *,
    key_provider: KeyProvider | None = None,
) -> TestClient:
    provider = key_provider or RemoteKeyProvider(ISSUER, make_fetch(public_jwks(new_key())))
    app = create_rs_app(
        make_settings(),
        key_provider=provider,
        internal_client=_internal_client(),
        rate_limiter=_limiter(),
    )
    return TestClient(app)


def test_prm_served_from_pinned_config(make_settings: MakeSettings) -> None:
    with _build(make_settings) as client:
        response = client.get(PRM_PATH)

    assert response.status_code == 200
    body = response.json()
    assert body["resource"] == RESOURCE
    assert body["authorization_servers"] == [ISSUER]
    assert body["scopes_supported"] == ["floresu:full"]
    assert response.headers["Cache-Control"] == "no-store"


def test_prm_also_served_under_the_mcp_suffix(make_settings: MakeSettings) -> None:
    with _build(make_settings) as client:
        response = client.get(f"{PRM_PATH}{MCP_PATH}")

    assert response.status_code == 200
    assert response.json()["resource"] == RESOURCE


def test_readyz_ok_when_jwks_reachable(make_settings: MakeSettings) -> None:
    with _build(make_settings) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["checks"]["as_jwks"]["ok"] is True


def test_readyz_degrades_to_503_when_jwks_unreachable(make_settings: MakeSettings) -> None:
    with _build(make_settings, key_provider=_FailingKeyProvider()) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["checks"]["as_jwks"]["ok"] is False


def test_healthz_is_always_ok(make_settings: MakeSettings) -> None:
    with _build(make_settings) as client:
        assert client.get("/healthz").json() == {"status": "ok"}


def test_metrics_exposes_http_and_tool_families(make_settings: MakeSettings) -> None:
    with _build(make_settings) as client:
        client.get("/healthz")  # generate one HTTP sample
        body = client.get("/metrics").text

    assert "http_requests_total" in body
    # The MCP domain counter family is registered and exposed alongside HTTP.
    assert "mcp_tool_invocations_total" in body


def test_unauthenticated_tool_call_is_challenged_on_both_paths(
    make_settings: MakeSettings,
) -> None:
    with _build(make_settings) as client:
        for path in (MCP_PATH, f"{MCP_PATH}/"):
            response = client.post(path, json=_TOOLS_LIST, headers=_MCP_HEADERS)
            assert response.status_code == 401, path
            challenge = response.headers["WWW-Authenticate"]
            assert challenge.startswith("Bearer resource_metadata=")
            assert PRM_PATH in challenge


def test_wrong_audience_token_is_rejected(make_settings: MakeSettings) -> None:
    key = new_key()
    app = create_rs_app(
        make_settings(),
        key_provider=RemoteKeyProvider(ISSUER, make_fetch(public_jwks(key))),
        internal_client=_internal_client(),
        rate_limiter=_limiter(),
    )
    wrong_aud = mint(key, aud="https://someone-else.example")
    with TestClient(app, base_url=RESOURCE) as client:
        response = client.post(
            f"{MCP_PATH}/",
            json=_TOOLS_LIST,
            headers={**_MCP_HEADERS, "Authorization": f"Bearer {wrong_aud}"},
        )

    assert response.status_code == 401


def test_valid_token_lists_the_tool_surface_on_both_paths() -> None:
    harness = AgentHarness(lambda _request: httpx.Response(200, json=[]))
    with harness.open() as client:
        # Post to both /mcp and /mcp/: neither may 307-redirect.
        no_slash = client.post(
            MCP_PATH,
            json=_TOOLS_LIST,
            headers={**_MCP_HEADERS, **harness._auth},
        )
        assert no_slash.status_code == 200, no_slash.text
        tools = harness.list_tools(client)

    # The read and write surfaces register onto one server (asserted in detail in
    # the per-domain tool tests), so this foundation check is a subset.
    assert {tool["name"] for tool in tools} >= _REPRESENTATIVE_TOOLS


def test_rs_dependency_facade_is_wired(make_settings: MakeSettings) -> None:
    provider = RemoteKeyProvider(ISSUER, make_fetch(public_jwks(new_key())))
    client = _internal_client()
    limiter = _limiter()
    app = create_rs_app(
        make_settings(), key_provider=provider, internal_client=client, rate_limiter=limiter
    )

    deps = get_rs_deps(app)

    assert deps.key_provider is provider
    assert deps.internal_client is client
    assert deps.rate_limiter is limiter


def test_build_app_composes_the_production_graph() -> None:
    # The production wiring builds without a live AS/Redis (both are lazy): the
    # app boots, serves the PRM, and challenges an unauthenticated tool call.
    settings = build_rs_settings()
    app = build_app(settings)
    with TestClient(app) as client:
        assert client.get(PRM_PATH).status_code == 200
        challenge = client.post(f"{MCP_PATH}/", json=_TOOLS_LIST, headers=_MCP_HEADERS)
        assert challenge.status_code == 401
