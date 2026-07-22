"""Test harness: drive the mounted MCP tools over the real transport.

Builds the actual resource-server app (:func:`create_rs_app`) with a faked JWKS
provider, a ``MockTransport``-backed internal client, and an in-memory rate-limit
store, then issues MCP ``tools/call`` / ``tools/list`` requests over the mounted
Streamable HTTP transport with a real minted bearer. This exercises the whole
path an agent hits (bearer boundary -> identity + actor on request.state -> scope
gate -> rate limit -> one internal HTTP call -> structured output), mocking only
the true external boundaries: the backend internal API and Redis.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr

from floresu_mcp.app import create_rs_app
from floresu_mcp.client import InternalApiClient
from floresu_mcp.keys import RemoteKeyProvider
from floresu_mcp.ratelimit import RateLimiter
from floresu_mcp.settings import SERVICE, RsSettings
from tests.fakes import InMemoryRateLimitStore
from tests.token_factory import ISSUER, RESOURCE, make_fetch, mint, new_key, public_jwks

if TYPE_CHECKING:
    from fastapi import FastAPI

BackendHandler = Callable[[httpx.Request], httpx.Response]
_INTERNAL_BASE = "http://backend:8001"
_API_TOKEN = "shared-internal-token"
_MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _settings() -> RsSettings:
    return RsSettings(
        service=SERVICE,
        environment="production",
        log_level="critical",
        host="127.0.0.1",
        port=9000,
        issuer=ISSUER,
        resource=RESOURCE,
        backend_internal_url=_INTERNAL_BASE,
        internal_api_token=SecretStr(_API_TOKEN),
        redis_url="redis://localhost:6379/0",
        rate_limit_window_seconds=60,
        rate_limit_request_budget=120,
        rate_limit_embed_write_budget=30,
    )


class AgentHarness:
    """A TestClient over the mounted MCP transport plus captured backend calls."""

    def __init__(
        self,
        backend: BackendHandler,
        *,
        sub: str = "user-42",
        client_id: str = "agent-client",
        scope: str | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        self.captured: list[httpx.Request] = []

        def capture(request: httpx.Request) -> httpx.Response:
            self.captured.append(request)
            return backend(request)

        key = new_key()
        provider = RemoteKeyProvider(ISSUER, make_fetch(public_jwks(key)))
        http = httpx.AsyncClient(base_url=_INTERNAL_BASE, transport=httpx.MockTransport(capture))
        self.store = InMemoryRateLimitStore()
        self._client = InternalApiClient(http, api_token=SecretStr(_API_TOKEN))
        self.app: FastAPI = create_rs_app(
            _settings(),
            key_provider=provider,
            internal_client=self._client,
            rate_limiter=limiter
            or RateLimiter(
                self.store, window_seconds=60, request_budget=120, embed_write_budget=30
            ),
        )
        minted = (
            mint(key, sub=sub, client_id=client_id)
            if scope is None
            else mint(key, sub=sub, client_id=client_id, scope=scope)
        )
        self._auth = {"Authorization": f"Bearer {minted}"}

    def _rpc(self, client: TestClient, method: str, params: dict[str, Any]) -> dict[str, Any]:
        response = client.post(
            "/mcp/",
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            headers={**_MCP_HEADERS, **self._auth},
        )
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    def call_tool(self, client: TestClient, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool; return its ``CallToolResult`` (``isError`` + content)."""
        body = self._rpc(client, "tools/call", {"name": name, "arguments": arguments})
        result: dict[str, Any] = body["result"]
        return result

    def list_tools(self, client: TestClient) -> list[dict[str, Any]]:
        body = self._rpc(client, "tools/list", {})
        tools: list[dict[str, Any]] = body["result"]["tools"]
        return tools

    def open(self) -> TestClient:
        return TestClient(self.app, base_url=RESOURCE)
