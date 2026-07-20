"""External app entrypoint (:8000).

Internet-reachable via the Cloudflare tunnel. The composition root that hosts the
public REST surface for the human web client. Built from the shared factory with
the external service identity injected; this slice adds the human session
boundary: the ``/auth`` + ``/me`` routers, the real cookie session verifier, the
inbound-identity strip, and (when configured) credentialed CORS for the SPA.
"""

from __future__ import annotations

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
from floresu.core.app_factory import create_app
from floresu.core.db import create_database, create_db_lifespan, db_readiness_check
from floresu.core.errors import build_exception_handlers
from floresu.core.identity import StripInboundIdentityMiddleware, deny_all_sessions, require_user
from floresu.core.settings import EXTERNAL_PORT, EXTERNAL_SERVICE, build_app_settings

if TYPE_CHECKING:
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

app: FastAPI = create_app(
    settings,
    routers=[accounts_router, me_router],
    readiness_checks=[db_readiness_check(db.engine)],
    exception_handlers=build_exception_handlers(),
    lifespan=create_db_lifespan(db.engine),
)
app.state.db = db
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
