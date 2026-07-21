"""MCP resource-server application assembly.

``create_rs_app`` wires the RS: structured logging, the public PRM + health +
``/metrics`` endpoints, the JWKS readiness check, and the bearer-auth boundary
guarding the MCP transport prefix. The token verifier, key provider, internal
client, and rate limiter are injected so tests substitute the network; ``build_app``
composes the production graph (httpx-backed JWKS discovery + internal client +
Redis-backed limiter) and manages their lifecycle.

The MCP tool transport that sits behind the bearer boundary is routed here: the
smoke tools via :func:`register_smoke_tools`. The full read/write tool surfaces
register onto the same server in later tickets.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import httpx
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mcp.server.fastmcp.server import StreamableHTTPASGIApp
from starlette.routing import Route
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from floresu_mcp.auth import BearerAuthMiddleware
from floresu_mcp.client import InternalApiClient, create_internal_http_client
from floresu_mcp.config import MCP_PATH, PRM_PATH
from floresu_mcp.correlation import CorrelationMiddleware
from floresu_mcp.health import create_health_router
from floresu_mcp.keys import JsonFetch, KeyProvider, RemoteKeyProvider, jwks_readiness_check
from floresu_mcp.logging import configure_logging, get_logger
from floresu_mcp.mcp_server import create_mcp_server
from floresu_mcp.metrics import instrument
from floresu_mcp.prm import build_prm_document
from floresu_mcp.ratelimit import RateLimiter, RedisRateLimitStore
from floresu_mcp.settings import RsSettings, build_rs_settings
from floresu_mcp.state import RsDeps, set_rs_deps
from floresu_mcp.tokens import AgentTokenVerifier
from floresu_mcp.tool_metrics import TOOL_METRICS_REGISTRY
from floresu_mcp.tools_smoke import register_smoke_tools

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from starlette.types import Lifespan

# Bound so a hung AS cannot pin the discovery/readiness call indefinitely.
_DISCOVERY_TIMEOUT_SECONDS = 10.0
# Metadata responses must not be cached by intermediaries.
_NO_STORE = {"Cache-Control": "no-store"}


def _compose_lifespan(
    session_manager: StreamableHTTPSessionManager,
    inner: Lifespan[FastAPI] | None,
) -> Lifespan[FastAPI]:
    """Wrap the MCP session manager's lifecycle around any injected lifespan.

    The routed Streamable HTTP transport requires its session manager running for
    the lifetime of the app; ``build_app`` additionally injects a lifespan that
    closes the network clients on shutdown."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with session_manager.run():
            if inner is None:
                yield
            else:
                async with inner(app):
                    yield

    return lifespan


def _create_prm_router(settings: RsSettings) -> APIRouter:
    """The public PRM endpoint (RFC 9728). Built from pinned config, not the host."""
    router = APIRouter(tags=["oauth"])
    document = build_prm_document(resource=settings.resource, issuer=settings.issuer)

    async def protected_resource_metadata() -> JSONResponse:
        return JSONResponse(document, headers=_NO_STORE)

    router.add_api_route(
        PRM_PATH,
        protected_resource_metadata,
        methods=["GET"],
        include_in_schema=False,
    )
    router.add_api_route(
        f"{PRM_PATH}{MCP_PATH}",
        protected_resource_metadata,
        methods=["GET"],
        include_in_schema=False,
    )
    return router


def create_rs_app(
    settings: RsSettings,
    *,
    key_provider: KeyProvider,
    internal_client: InternalApiClient,
    rate_limiter: RateLimiter,
    lifespan: Lifespan[FastAPI] | None = None,
) -> FastAPI:
    """Assemble the resource-server app from injected dependencies."""
    configure_logging(environment=settings.environment, log_level=settings.log_level)
    log = get_logger(settings.service)

    verifier = AgentTokenVerifier(key_provider, issuer=settings.issuer, resource=settings.resource)

    # The MCP tool surface: register the smoke tools onto the shared server, then
    # route its Streamable HTTP transport under the bearer-guarded MCP prefix.
    # Calling streamable_http_app() has the side effect of creating the session
    # manager (its property raises otherwise); the returned sub-app is not mounted
    # (a Mount would 307-redirect /mcp -> /mcp/, see the explicit routes below).
    mcp = create_mcp_server(settings)
    register_smoke_tools(mcp, internal_client, rate_limiter)
    mcp.streamable_http_app()
    transport = StreamableHTTPASGIApp(mcp.session_manager)

    app = FastAPI(
        title=f"floresu ({settings.service})",
        version="0.1.0",
        lifespan=_compose_lifespan(mcp.session_manager, lifespan),
    )
    app.state.settings = settings
    app.state.log = log
    # The injected seams the RS exposes, behind one typed façade.
    set_rs_deps(
        app,
        RsDeps(
            key_provider=key_provider,
            token_verifier=verifier,
            internal_client=internal_client,
            rate_limiter=rate_limiter,
        ),
    )

    app.include_router(_create_prm_router(settings))
    app.include_router(create_health_router([jwks_readiness_check(key_provider)]))
    # Serve POST /mcp (no slash) directly, matching /mcp/. Two explicit full-match
    # routes bound to the bare ASGI transport: an outer Mount only PARTIAL-matches
    # /mcp, so redirect_slashes emits a 307 -> /mcp/ that stalls https->http MCP
    # clients (~30s). StreamableHTTPASGIApp ignores the leftover path, so both
    # routes delegate identically to the session manager.
    app.router.routes.append(Route(MCP_PATH, transport))
    app.router.routes.append(Route(f"{MCP_PATH}/", transport))

    # The agent trust boundary: guard the MCP transport prefix. Added before
    # instrument() so the metrics middleware wraps it and counts the boundary's
    # 401s too.
    app.add_middleware(
        BearerAuthMiddleware,
        verifier=verifier,
        resource=settings.resource,
        protected_prefix=MCP_PATH,
    )
    instrument(app, TOOL_METRICS_REGISTRY)

    # Correlation is mounted here so it is outermost among the always-on
    # middleware: request_id is bound before the metrics middleware, the bearer
    # guard, and the tool layer run, so the non-guarded paths (/healthz, /metrics,
    # PRM) are correlated too. In production ProxyHeadersMiddleware is added after
    # this and becomes the true outermost layer, rewriting the scheme first.
    app.add_middleware(CorrelationMiddleware, service=settings.service)
    if settings.allowed_cors_origins:
        # Dev-only: the browser MCP Inspector runs OAuth discovery and
        # token-exchange fetches from its own origin, so it needs CORS. Mounted
        # outermost so a preflight to the bearer-guarded /mcp transport clears
        # CORS before the guard 401s it.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    if settings.trusted_proxies:
        # Trust X-Forwarded-* only from the pinned app-net CIDR (never ``*``) so
        # the tunnel's plaintext http is rewritten to https for absolute URLs.
        # Added last, so it is outermost and runs before correlation and the
        # bearer guard. Empty in dev -> not mounted.
        app.add_middleware(
            ProxyHeadersMiddleware,
            trusted_hosts=settings.trusted_proxies,
        )

    log.info(
        "mcp_configured",
        environment=settings.environment,
        port=settings.port,
        issuer=settings.issuer,
        resource=settings.resource,
    )
    return app


def create_json_fetch(client: httpx.AsyncClient) -> JsonFetch:
    """Adapt an ``httpx.AsyncClient`` to the key provider's ``JsonFetch`` seam,
    keeping :mod:`floresu_mcp.keys` free of any HTTP-library dependency."""

    async def fetch(url: str) -> dict[str, Any]:
        response = await client.get(url)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    return fetch


def build_app(settings: RsSettings | None = None) -> FastAPI:
    """Compose the production RS: httpx-backed JWKS discovery + internal client +
    a Redis-backed rate limiter, with the network clients closed on shutdown."""
    settings = settings or build_rs_settings()

    # Imported here (not at module scope) so unit tests that inject their own
    # dependencies into create_rs_app never require the redis package graph.
    from redis.asyncio import Redis

    discovery_client = httpx.AsyncClient(timeout=_DISCOVERY_TIMEOUT_SECONDS)
    key_provider = RemoteKeyProvider(settings.issuer, create_json_fetch(discovery_client))
    internal_http = create_internal_http_client(settings)
    internal_client = InternalApiClient(internal_http, api_token=settings.internal_api_token)
    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
    rate_limiter = RateLimiter(
        RedisRateLimitStore(redis),
        window_seconds=settings.rate_limit_window_seconds,
        request_budget=settings.rate_limit_request_budget,
        embed_write_budget=settings.rate_limit_embed_write_budget,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await asyncio.gather(discovery_client.aclose(), internal_http.aclose(), redis.aclose())

    return create_rs_app(
        settings,
        key_provider=key_provider,
        internal_client=internal_client,
        rate_limiter=rate_limiter,
        lifespan=lifespan,
    )
