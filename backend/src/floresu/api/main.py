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
from floresu.audit.wiring import build_write_event_publisher
from floresu.core.actor import resolve_web_actor
from floresu.core.app_factory import create_app
from floresu.core.db import create_database, create_db_lifespan, db_readiness_check
from floresu.core.errors import build_exception_handlers
from floresu.core.identity import StripInboundIdentityMiddleware, deny_all_sessions, require_user
from floresu.core.settings import EXTERNAL_PORT, EXTERNAL_SERVICE, build_app_settings
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
from floresu.profile.wiring import build_source_service_provider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI

settings = build_app_settings(service=EXTERNAL_SERVICE, port=EXTERNAL_PORT)
db = create_database(settings.database_url)

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


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Dispose the DB pool on shutdown and run the stale-client reaper in between."""
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


app: FastAPI = create_app(
    settings,
    routers=[accounts_router, me_router, oauth_router, sources_router],
    readiness_checks=[db_readiness_check(db.engine)],
    exception_handlers={**build_exception_handlers(), **build_oauth_exception_handlers()},
    lifespan=_lifespan,
)
app.state.db = db
# The write-event seam, composed with the audit consumer as the sole transactional
# consumer. Domain slices publish through this; later slices register the SSE and
# embed side channels here as best-effort consumers.
app.state.events = build_write_event_publisher()
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
