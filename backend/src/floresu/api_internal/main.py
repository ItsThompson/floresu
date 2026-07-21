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
from floresu.library.router import create_bullets_router
from floresu.library.wiring import build_bullet_service_provider
from floresu.profile.router import create_sources_router
from floresu.profile.skills.router import create_skills_router
from floresu.profile.skills.wiring import build_skill_service_provider
from floresu.profile.variants.router import create_variants_router
from floresu.profile.variants.wiring import build_variant_service_provider
from floresu.profile.wiring import build_source_service_provider
from floresu.rendering.wiring import build_render_module
from floresu.resumes.render_router import create_resume_render_router
from floresu.resumes.render_wiring import build_resume_render_service_provider
from floresu.resumes.router import create_resumes_router
from floresu.resumes.wiring import build_resume_service_provider
from floresu.storage.wiring import build_object_store
from floresu.worklog.router import create_worklog_router
from floresu.worklog.wiring import build_worklog_service_provider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI

settings = build_app_settings(service=INTERNAL_SERVICE, port=INTERNAL_PORT)
db = create_database(settings.database_url)

# The one embedding provider (the only external AI dependency), injected into both
# the worker-facing embed routes and the synchronous fast-path. Its httpx client is
# closed on shutdown by the lifespan below.
openai_client = create_openai_http_client(settings)
embedding_provider = create_embedding_provider(openai_client)

# Product routers, mounted with the trusted-header identity and the named-agent
# actor. The same routers mount on the external app with the human boundary; the
# service, transaction, and write-event publish live once in the domain layer.
sources_router = create_sources_router(
    build_source_service_provider(),
    identity=require_internal_user,
    actor=resolve_internal_actor,
)
worklog_router = create_worklog_router(
    build_worklog_service_provider(),
    identity=require_internal_user,
    actor=resolve_internal_actor,
)
bullets_router = create_bullets_router(
    build_bullet_service_provider(),
    identity=require_internal_user,
    actor=resolve_internal_actor,
)
skills_router = create_skills_router(
    build_skill_service_provider(),
    identity=require_internal_user,
    actor=resolve_internal_actor,
)
variants_router = create_variants_router(
    build_variant_service_provider(),
    identity=require_internal_user,
    actor=resolve_internal_actor,
)
resumes_router = create_resumes_router(
    build_resume_service_provider(),
    identity=require_internal_user,
    actor=resolve_internal_actor,
)
# Resume rendering on the agent-facing internal app: trusted-header identity + agent
# actor. Mounted before the resumes router so GET /resumes/templates matches ahead of
# GET /resumes/{resume_id}.
render_module = build_render_module()
object_store = build_object_store(settings)
resume_render_router = create_resume_render_router(
    build_resume_render_service_provider(render_module, object_store),
    identity=require_internal_user,
    actor=resolve_internal_actor,
)
# Worker-facing embed routes (internal app only): the arq worker reads an item's
# text and writes its vector back over these. The gate, provider call, and
# transaction live in the service.
embed_router = create_embedding_router(
    build_embedding_service_provider(embedding_provider),
    identity=require_internal_user,
)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Dispose the DB pool on shutdown and close the embedding provider client."""
    async with create_db_lifespan(db.engine)(app):
        try:
            yield
        finally:
            await openai_client.aclose()


app: FastAPI = create_app(
    settings,
    routers=[
        sources_router,
        worklog_router,
        bullets_router,
        skills_router,
        variants_router,
        resume_render_router,
        resumes_router,
        embed_router,
    ],
    readiness_checks=[db_readiness_check(db.engine)],
    exception_handlers=build_exception_handlers(),
    lifespan=_lifespan,
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


def main() -> None:  # pragma: no cover - process entrypoint
    import uvicorn

    uvicorn.run("floresu.api_internal.main:app", host=settings.host, port=settings.port)
