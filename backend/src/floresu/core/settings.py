"""Application settings.

Deployment-wide configuration is sourced from the environment once
(:class:`EnvSettings`) and is identical for both apps. Per-app identity (the
``service`` name and ``port``) is injected at construction time so the external
and internal apps differ *only* by their injected settings, per the two-app split.

Later slices extend this with the identity, OAuth, and Redis knobs their features
need; the core kit keeps only what both apps and the DB layer require.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# EnvSettings must load the canonical repo-root .env regardless of the process
# CWD (a host inner loop may launch uvicorn from backend/). Anchor it to the repo
# root from this file's location. Compose/CD inject real env vars, which always
# win over env_file, so this affects only the host-run inner loop.
ROOT_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"

# Per-app identity. Service names are bound onto every structlog line so external
# and internal traffic is distinguishable in aggregated logs.
EXTERNAL_SERVICE = "floresu-external"
INTERNAL_SERVICE = "floresu-internal"
EXTERNAL_PORT = 8000
INTERNAL_PORT = 8001


class EnvSettings(BaseSettings):
    """Deployment-wide config shared by both apps, sourced from the environment.

    Field names mirror the shared ``.env`` keys (``ENVIRONMENT``, ``LOG_LEVEL``,
    ``DATABASE_URL``). Unknown keys are ignored so the single sectioned root
    ``.env`` can carry vars for other consumers (e.g. ``REDIS_URL``).
    """

    model_config = SettingsConfigDict(env_file=ROOT_ENV_FILE, extra="ignore")

    environment: str = "development"
    log_level: str = "info"
    host: str = "0.0.0.0"  # container binds all interfaces; ingress is tunnel-only
    # Async SQLAlchemy URL (asyncpg driver). Dev default targets the Postgres in
    # docker-compose.yml published to localhost; prod injects the in-network form.
    database_url: str = "postgresql+asyncpg://floresu:floresu@localhost:5432/floresu"
    # Shared secret gating the internal trust boundary. Empty by default so the
    # internal boundary fails closed (denies) until a token is provisioned; prod
    # injects a real secret and the MCP server presents the same value.
    internal_api_token: str = ""
    # HS256 secret for human session JWTs (external app), separate from the agent
    # OAuth keypair (a later slice). Empty by default so an unconfigured external
    # app fail-safe denies every session (no cookie resolves). SecretStr so an
    # accidental settings dump/log masks it; read via .get_secret_value() only at
    # JWT sign/verify.
    session_jwt_secret: SecretStr = SecretStr("")
    # Cookie Domain for the session cookie. Prod pins the apex so the SPA and API
    # subdomains share it; empty in dev makes the cookie host-only (localhost).
    cookie_domain: str = ""
    # Allowed browser origin for the SPA's credentialed login/session XHRs (CORS).
    # Empty in dev, where the SPA reaches the API same-origin via the Vite dev
    # proxy; prod pins the SPA origin so the cross-subdomain cookie flow works.
    cors_origin: str = ""


class AppSettings(BaseModel):
    """Full settings for one ASGI app: shared env config plus per-app identity."""

    service: str
    port: int
    environment: str
    log_level: str
    host: str
    database_url: str
    internal_api_token: str = ""
    # Auth knobs, defaulted so the shared test settings factory and any non-auth
    # caller need not supply them.
    session_jwt_secret: SecretStr = SecretStr("")
    cookie_domain: str = ""
    cors_origin: str = ""

    @property
    def is_dev(self) -> bool:
        return self.environment.lower() == "development"

    @property
    def allowed_cors_origins(self) -> list[str]:
        """Browser origins allowed to send credentialed XHRs; empty when unset."""
        return [self.cors_origin] if self.cors_origin else []


def build_app_settings(*, service: str, port: int, env: EnvSettings | None = None) -> AppSettings:
    """Compose per-app settings from injected identity and shared env config."""
    env = env or EnvSettings()
    return AppSettings(
        service=service,
        port=port,
        environment=env.environment,
        log_level=env.log_level,
        host=env.host,
        database_url=env.database_url,
        internal_api_token=env.internal_api_token,
        session_jwt_secret=env.session_jwt_secret,
        cookie_domain=env.cookie_domain,
        cors_origin=env.cors_origin,
    )
