"""Internal app entrypoint (:8001).

Never tunnel-routed and never host-published: reachable in-network by first-party
``app-net`` containers only (the MCP server is its intended caller). The
composition root for the trusted-header surface the agent path calls. Built from
the shared factory with the internal service identity injected, differing from the
external app only by these settings; the trusted-header identity boundary is
layered on by the internal-boundary slice.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from floresu import models_registry as _models_registry  # noqa: F401
from floresu.api.app_builder import build_shared_router_block
from floresu.audit.wiring import build_write_event_publisher
from floresu.core.actor import resolve_internal_actor
from floresu.core.app_factory import create_app
from floresu.core.db import create_database, create_db_lifespan, db_readiness_check
from floresu.core.errors import build_exception_handlers
from floresu.core.identity import require_internal_user
from floresu.core.settings import INTERNAL_PORT, INTERNAL_SERVICE, build_app_settings
from floresu.embedding.enqueue import build_sync_embed_fastpath_consumer
from floresu.embedding.router import create_embedding_router
from floresu.embedding.wiring import (
    build_embedding_service_provider,
    create_embedding_provider,
    create_openai_http_client,
    embedding_resolver,
)
from floresu.resumes.cow import EditChannel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI


def create_internal_app() -> FastAPI:
    """Build the in-network internal app (:8001).

    Wires the agent-facing embed routes and the synchronous embed fast-path around
    the shared router block, injecting the trusted-header identity, the named-agent
    actor, the MCP resume edit channel, and the one embedding provider.
    """
    settings = build_app_settings(service=INTERNAL_SERVICE, port=INTERNAL_PORT)
    db = create_database(settings.database_url)

    # The one embedding provider (the only external AI dependency), injected into both
    # the worker-facing embed routes and the synchronous fast-path. Its httpx client is
    # closed on shutdown by the lifespan below.
    openai_client = create_openai_http_client(settings)
    embedding_provider = create_embedding_provider(openai_client)

    # The eleven product routers both apps share, injected with the trusted-header
    # identity, the named-agent actor, and the MCP resume edit channel; search embeds
    # the query via the one embedding provider.
    shared_routers = build_shared_router_block(
        settings,
        identity=require_internal_user,
        actor=resolve_internal_actor,
        channel=EditChannel.MCP,
        search_provider=embedding_provider,
    )

    # Worker-facing embed routes (internal app only): the arq worker reads an item's
    # text and writes its vector back over these. The gate, provider call, and
    # transaction live in the service.
    embed_router = create_embedding_router(
        build_embedding_service_provider(embedding_provider),
        identity=require_internal_user,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Dispose the DB pool on shutdown and close the embedding provider client."""
        async with create_db_lifespan(db.engine)(app):
            try:
                yield
            finally:
                await openai_client.aclose()

    app = create_app(
        settings,
        routers=[*shared_routers, embed_router],
        readiness_checks=[db_readiness_check(db.engine)],
        exception_handlers=build_exception_handlers(),
        lifespan=lifespan,
    )
    app.state.db = db
    # The write-event seam. The audit consumer is the transactional consumer; the
    # synchronous embed fast-path is the post-commit side channel, so an agent's
    # write-then-search in one turn sees the semantic vector without waiting on the
    # worker. A rolled-back write embeds nothing; a failed embed never fails the write.
    app.state.events = build_write_event_publisher(
        post_commit=[
            build_sync_embed_fastpath_consumer(
                db.sessionmaker, embedding_resolver(), embedding_provider
            )
        ]
    )
    return app


# Retained so the uvicorn string entrypoint "floresu.api_internal.main:app", the
# console script, and the tests that import the module-global keep working.
app: FastAPI = create_internal_app()


def main() -> None:  # pragma: no cover - process entrypoint
    import uvicorn

    uvicorn.run(
        "floresu.api_internal.main:app", host=app.state.settings.host, port=app.state.settings.port
    )
