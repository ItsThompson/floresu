"""External app entrypoint (:8000).

Internet-reachable via the Cloudflare tunnel. The composition root that hosts the
public REST surface for the human web client. Built from the shared factory with
the external service identity injected; this slice adds the human session
boundary: the ``/auth`` + ``/me`` routers, the real cookie session verifier, the
inbound-identity strip, and (when configured) credentialed CORS for the SPA.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import timedelta
from typing import TYPE_CHECKING

from fastapi.middleware.cors import CORSMiddleware

from floresu.accounts.api import create_accounts_router
from floresu.accounts.config import (
    build_cookie_config,
    build_session_config,
    validate_session_secret,
)
from floresu.accounts.me_api import create_me_router
from floresu.accounts.passwords import BcryptPasswordHasher
from floresu.accounts.session import build_revocation_lookup, create_session_verifier
from floresu.accounts.tokens import SessionTokenCodec
from floresu.accounts.wiring import build_account_service_provider
from floresu.audit.wiring import build_audit_service_provider, build_write_event_publisher
from floresu.core.actor import resolve_web_actor
from floresu.core.app_factory import create_app
from floresu.core.db import create_database, create_db_lifespan, db_readiness_check
from floresu.core.errors import build_exception_handlers
from floresu.core.identity import StripInboundIdentityMiddleware, deny_all_sessions, require_user
from floresu.core.redis import create_redis_client
from floresu.core.settings import EXTERNAL_PORT, EXTERNAL_SERVICE, build_app_settings
from floresu.embedding.enqueue import build_async_embed_enqueue_consumer
from floresu.embedding.wiring import (
    build_embed_queue,
    create_embedding_provider,
    create_openai_http_client,
)
from floresu.feed.api import create_feed_router
from floresu.feed.store import RedisFeedStore
from floresu.feed.wiring import FEED_STORE_ATTR, build_sse_feed_consumer
from floresu.jobapps.router import create_jobapps_router
from floresu.jobapps.wiring import build_jobapps_service_provider
from floresu.library.router import create_bullets_router
from floresu.library.wiring import build_bullet_service_provider
from floresu.lifecycle.router import create_lifecycle_router
from floresu.lifecycle.wiring import build_lifecycle_service_provider
from floresu.oauth.api import create_oauth_router
from floresu.oauth.cleanup import start_stale_client_cleanup, stop_stale_client_cleanup
from floresu.oauth.config import build_oauth_config
from floresu.oauth.errors import build_oauth_exception_handlers
from floresu.oauth.keys import load_signing_key_set
from floresu.oauth.tokens import AccessTokenCodec
from floresu.oauth.wiring import (
    build_authorization_service_provider,
    build_token_service_provider,
)
from floresu.profile.router import create_sources_router
from floresu.profile.skills.router import create_skills_router
from floresu.profile.skills.wiring import build_skill_service_provider
from floresu.profile.variants.router import create_variants_router
from floresu.profile.variants.wiring import build_variant_service_provider
from floresu.profile.wiring import build_source_service_provider
from floresu.rendering.wiring import build_render_module
from floresu.resumes.cow import EditChannel
from floresu.resumes.finalize_router import create_resume_finalize_router
from floresu.resumes.finalize_wiring import build_resume_finalize_service_provider
from floresu.resumes.render_router import create_resume_render_router
from floresu.resumes.render_wiring import build_resume_render_service_provider
from floresu.resumes.router import create_resumes_router
from floresu.resumes.wiring import build_resume_service_provider
from floresu.search.router import create_search_router
from floresu.search.wiring import build_search_service_provider
from floresu.storage.wiring import build_object_store
from floresu.worklog.router import create_worklog_router
from floresu.worklog.wiring import build_worklog_service_provider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI

settings = build_app_settings(service=EXTERNAL_SERVICE, port=EXTERNAL_PORT)
db = create_database(settings.database_url)
# One async Redis client for the app, shared by the feed store. The activity feed
# is the first consumer; later slices reuse it for the queue and rate limits.
redis_client = create_redis_client(settings.redis_url)
feed_store = RedisFeedStore(redis_client)
# The arq queue the embed jobs are enqueued onto (worker-drained). Human/web writes
# take this asynchronous path; the agent path uses the internal app's fast-path.
embed_queue = build_embed_queue(settings.redis_url)
# The embedding provider used to embed the search query on this app (the only
# external AI dependency). Query embedding is best-effort: search degrades to
# lexical-only and surfaces a soft notice when it is unavailable. The httpx client
# is closed on shutdown by the lifespan below.
search_query_client = create_openai_http_client(settings)
search_embedding_provider = create_embedding_provider(search_query_client)

# Human session cookies: HS256 codec + bcrypt hasher wired into the /auth router
# and the real cookie verifier behind require_user.
session_config = build_session_config(settings)
# Fail fast on a missing/weak secret outside development (dev stays lenient and
# fail-safe denies), so a prod misconfig cannot silently mint unusable tokens.
validate_session_secret(session_config, is_dev=settings.is_dev)
cookie_config = build_cookie_config(settings)
codec = SessionTokenCodec(session_config)
service_provider = build_account_service_provider(BcryptPasswordHasher(), codec)
accounts_router = create_accounts_router(service_provider, cookie_config=cookie_config)
# GET /me resolves the human session via require_user and reuses the same service
# provider. External app only.
me_router = create_me_router(service_provider, identity=require_user)

# Agent OAuth 2.1 Authorization Server. All issuer/metadata/endpoint URLs are
# built from pinned config (the Site-URL gotcha); the signing key is loaded from
# the mounted PEM (or an ephemeral dev keypair). Fails fast outside development
# when no key is configured, like the session secret.
oauth_config = build_oauth_config(settings)
oauth_keyset = load_signing_key_set(oauth_config, is_dev=settings.is_dev)
oauth_codec = AccessTokenCodec(oauth_keyset, oauth_config)
oauth_router = create_oauth_router(
    config=oauth_config,
    keyset=oauth_keyset,
    authorization_provider=build_authorization_service_provider(oauth_config),
    token_provider=build_token_service_provider(oauth_config, oauth_codec),
)

# Profile sources, mounted with the human session identity and a human actor. The
# internal app mounts the same router with the trusted-header identity and the
# named-agent actor; the service, transaction, and write-event publish live once
# in the domain layer.
sources_router = create_sources_router(
    build_source_service_provider(),
    identity=require_user,
    actor=resolve_web_actor,
)

# Worklog entries, tags, and source attachment, mounted with the human session
# identity and a human actor. The internal app mounts the same router with the
# trusted-header identity and the named-agent actor.
worklog_router = create_worklog_router(
    build_worklog_service_provider(),
    identity=require_user,
    actor=resolve_web_actor,
)

# Canonical library bulletpoints and the provenance DAG, mounted with the human
# session identity and a human actor. The internal app mounts the same router with
# the trusted-header identity and the named-agent actor.
bullets_router = create_bullets_router(
    build_bullet_service_provider(),
    identity=require_user,
    actor=resolve_web_actor,
)

# Curated skills and identity variants: the non-source profile family. Mounted with
# the human session identity and a human actor; the internal app mounts the same
# routers with the trusted-header identity and the named-agent actor.
skills_router = create_skills_router(
    build_skill_service_provider(),
    identity=require_user,
    actor=resolve_web_actor,
)
variants_router = create_variants_router(
    build_variant_service_provider(),
    identity=require_user,
    actor=resolve_web_actor,
)

# Resumes: the JSONB-authoritative Output layer. Mounted with the human session
# identity and a human actor; the internal app mounts the same router with the
# trusted-header identity and the named-agent actor.
resumes_router = create_resumes_router(
    build_resume_service_provider(),
    identity=require_user,
    actor=resolve_web_actor,
    channel=EditChannel.WEB,
)

# Resume rendering: preview streams ephemeral bytes; export persists a PDF to R2 and
# records the object key. The render module (typst-py) and the R2 object store are
# process-wide and injected into the request-scoped service. Mounted before the
# resumes router so GET /resumes/templates matches ahead of GET /resumes/{resume_id}.
render_module = build_render_module()
object_store = build_object_store(settings)
resume_render_router = create_resume_render_router(
    build_resume_render_service_provider(render_module, object_store),
    identity=require_user,
    actor=resolve_web_actor,
)

# Finalize an application resume (freeze references to inline read-only text, snapshot
# the identity, render + store the frozen PDF, submit a linked application). Reuses the
# process-wide render module and R2 object store. The suffix path never collides with
# GET /resumes/{resume_id}, so mounting order is irrelevant.
resume_finalize_router = create_resume_finalize_router(
    build_resume_finalize_service_provider(render_module, object_store),
    identity=require_user,
    actor=resolve_web_actor,
)

# Job applications: the lightweight relational entity whose ``submitted`` status
# finalizes the linked 1:1 resume. The submit trigger delegates to the finalizer built
# from the same render module and object store. Mounted with the human session identity
# and a human actor; the internal app mounts the same router for the agent path.
jobapps_router = create_jobapps_router(
    build_jobapps_service_provider(render_module, object_store),
    identity=require_user,
    actor=resolve_web_actor,
)

# Web-human-only lifecycle: restore is served by each domain router; this router
# adds the destructive/recovery surface (permanent delete per entity, data export,
# account deletion) that must never reach an agent. Mounted on the external app
# ONLY, with the human session identity and a human actor; a boundary test asserts
# it is absent from the internal app. Account deletion clears the session cookies,
# so the cookie policy is injected.
lifecycle_router = create_lifecycle_router(
    build_lifecycle_service_provider(),
    identity=require_user,
    actor=resolve_web_actor,
    cookie_config=cookie_config,
)


# The live activity feed: GET /feed (SSE stream) + GET /feed/history (initial load).
# The stream resolves the caller via require_user and reads the process-wide feed
# store off app.state; history reads the audit activity-feed via its own service.
feed_router = create_feed_router(
    identity=require_user, audit_service_provider=build_audit_service_provider()
)

# Hybrid search backing the Library search view: read-only, human session identity.
# Embeds the query via the app's provider and degrades to lexical-only on failure.
search_router = create_search_router(
    build_search_service_provider(search_embedding_provider),
    identity=require_user,
)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Dispose the DB pool and Redis on shutdown; run the stale-client reaper in between."""
    async with create_db_lifespan(db.engine)(app):
        # Reap stale open-registration OAuth clients on a background task so DCR
        # rows stay bounded; stopped on shutdown before the pool is disposed.
        cleanup_task = start_stale_client_cleanup(
            db.sessionmaker,
            oauth_config,
            oauth_codec,
            interval=timedelta(seconds=settings.oauth_client_cleanup_interval_seconds),
            max_age=timedelta(seconds=settings.oauth_stale_client_max_age_seconds),
        )
        try:
            yield
        finally:
            await stop_stale_client_cleanup(cleanup_task)
            await embed_queue.aclose()
            await search_query_client.aclose()
            await redis_client.aclose()


app: FastAPI = create_app(
    settings,
    routers=[
        accounts_router,
        me_router,
        oauth_router,
        sources_router,
        worklog_router,
        bullets_router,
        skills_router,
        variants_router,
        feed_router,
        resume_render_router,
        resume_finalize_router,
        jobapps_router,
        resumes_router,
        search_router,
        lifecycle_router,
    ],
    readiness_checks=[db_readiness_check(db.engine)],
    exception_handlers={**build_exception_handlers(), **build_oauth_exception_handlers()},
    lifespan=_lifespan,
)
app.state.db = db
# The write-event seam, composed with the audit consumer as the sole transactional
# consumer and two post-commit side channels: the SSE feed publish and the async
# embed enqueue. A committed content write fans out to the user's Redis feed
# channel and enqueues one embed job; a rolled-back write does neither.
app.state.events = build_write_event_publisher(
    post_commit=[
        build_sse_feed_consumer(feed_store),
        build_async_embed_enqueue_consumer(embed_queue),
    ]
)
# The feed store the SSE endpoint streams from (resolved via get_feed_store).
setattr(app.state, FEED_STORE_ATTR, feed_store)
# Replace the deny-all default with the real signed-JWT + sid-blacklist verifier.
# With no configured SESSION_JWT_SECRET the app fail-safe denies every session
# rather than sign/verify with an empty key.
app.state.session_verifier = (
    create_session_verifier(codec, build_revocation_lookup(db))
    if session_config.secret.get_secret_value()
    else deny_all_sessions
)
# Strip any client-supplied X-User-ID app-wide: the external app never trusts it.
app.add_middleware(StripInboundIdentityMiddleware)
# CORS for credentialed browser XHRs from the SPA origin. Added last so it is the
# outermost middleware and handles preflight before the identity strip. Empty in
# dev (SPA reaches the API same-origin via the Vite proxy), so it is not mounted.
if settings.allowed_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def main() -> None:  # pragma: no cover - process entrypoint
    import uvicorn

    uvicorn.run("floresu.api.main:app", host=settings.host, port=settings.port)
