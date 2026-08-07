"""External app entrypoint (:8000).

Internet-reachable via the Cloudflare tunnel. The composition root that hosts the
public REST surface for the human web client. Built from the shared factory with
the external service identity injected, and it adds the human session
boundary: the ``/auth`` + ``/me`` routers, the real cookie session verifier, the
inbound-identity strip, and (when configured) credentialed CORS for the SPA.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import timedelta
from typing import TYPE_CHECKING

from fastapi.middleware.cors import CORSMiddleware

from floresu import models_registry as _models_registry  # noqa: F401
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
from floresu.api.app_builder import build_shared_router_block
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
from floresu.resumes.cow import EditChannel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI


def create_external_app() -> FastAPI:
    """Build the internet-facing external app (:8000).

    Wires the human-session boundary (accounts/me, OAuth, feed, lifecycle, the
    cookie session verifier, the inbound-identity strip, and credentialed CORS)
    around the shared router block, injecting the human identity, the web actor,
    the web resume edit channel, and the search-query embedding provider.
    """
    settings = build_app_settings(service=EXTERNAL_SERVICE, port=EXTERNAL_PORT)
    db = create_database(settings.database_url)
    # One async Redis client for the app, shared by the feed store, the embed queue,
    # and the rate-limit counters.
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

    # The eleven product routers both apps share, injected with the human session
    # identity, the web actor, and the web resume edit channel; search embeds the
    # query via this app's best-effort provider, degrading to lexical-only on failure.
    shared_routers = build_shared_router_block(
        settings,
        identity=require_user,
        actor=resolve_web_actor,
        channel=EditChannel.WEB,
        search_provider=search_embedding_provider,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
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

    app = create_app(
        settings,
        routers=[
            accounts_router,
            me_router,
            oauth_router,
            feed_router,
            *shared_routers,
            lifecycle_router,
        ],
        readiness_checks=[db_readiness_check(db.engine)],
        exception_handlers={**build_exception_handlers(), **build_oauth_exception_handlers()},
        lifespan=lifespan,
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
    return app


# Retained so the uvicorn string entrypoint "floresu.api.main:app", the console
# script, and the tests that import the module-global keep working.
app: FastAPI = create_external_app()


def main() -> None:  # pragma: no cover - process entrypoint
    import uvicorn

    uvicorn.run("floresu.api.main:app", host=app.state.settings.host, port=app.state.settings.port)
