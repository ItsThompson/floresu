"""Application settings.

Deployment-wide configuration is sourced from the environment once
(:class:`EnvSettings`) and is identical for both apps. Per-app identity (the
``service`` name and ``port``) is injected at construction time so the external
and internal apps differ *only* by their injected settings, per the two-app split.

This holds the knobs both apps and the DB layer require, plus the identity, OAuth,
and Redis knobs the domains layer on top.
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
    # Redis URL. Backs the SSE activity feed (per-user pub/sub channel + bounded
    # replay buffer), the arq queue, and the rate-limit counters. Dev default
    # targets the Redis in docker-compose.yml on localhost.
    redis_url: str = "redis://localhost:6379/0"
    # Shared secret gating the internal trust boundary. Empty by default so the
    # internal boundary fails closed (denies) until a token is provisioned; prod
    # injects a real secret and the MCP server presents the same value.
    internal_api_token: str = ""
    # HS256 secret for human session JWTs (external app), separate from the agent
    # OAuth keypair. Empty by default so an unconfigured external app fail-safe
    # denies every session (no cookie resolves). SecretStr so an
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
    # Discord Incoming Webhook the external app posts to on a successful signup.
    # Empty by default so the notification path is a no-op when unconfigured.
    discord_webhook_url: SecretStr = SecretStr("")
    # Pinned public URLs the OAuth 2.1 AS derives every issuer/metadata/endpoint
    # URL from (the "Site-URL gotcha": the tunnel reaches the origin as
    # http://backend:8000, so a request-derived URL would break client issuer/
    # audience validation). ``public_base_url`` is the AS origin and token ``iss``;
    # ``app_public_url`` is the SPA that renders consent; ``mcp_public_url`` is the
    # MCP resource agent access tokens are audience-bound to.
    public_base_url: str = "http://localhost:8000"
    app_public_url: str = "http://localhost:5173"
    mcp_public_url: str = "http://localhost:9000"
    # Agent OAuth 2.1 AS signing key: the AS holds a private RSA PEM and publishes
    # the public key via JWKS; ``oauth_key_id`` is the active ``kid``. An empty
    # path lets development generate an ephemeral in-memory keypair so the app
    # boots without a mounted PEM; outside development a missing key fails fast.
    oauth_private_key_path: str = ""
    oauth_key_id: str = "floresu-oauth-dev"
    # Agent token lifetimes: short-lived access token + long rotating refresh.
    oauth_access_ttl_seconds: int = 900
    oauth_refresh_ttl_seconds: int = 2_592_000
    # Stale-client reaper (external app). Dynamic Client Registration is open at
    # P0, so registration rows would grow unbounded; a periodic sweep reaps
    # clients whose registration is older than the max age (cascade-revoking each
    # reaped client's grant + refresh chain). A non-positive interval disables it.
    oauth_client_cleanup_interval_seconds: int = 21_600
    oauth_stale_client_max_age_seconds: int = 2_592_000
    # Embedding provider (the only external AI dependency). The API key is empty by
    # default so a dev/test box needs no OpenAI account: the synchronous fast-path
    # then fails soft (best-effort) and items stay lexically searchable. The base
    # URL is overridable for a proxy or a stub. The model + dimension are pinned in
    # ``floresu.embedding.config`` (changing them is a migration), so they are not
    # tunable settings.
    openai_api_key: SecretStr = SecretStr("")
    openai_base_url: str = "https://api.openai.com"
    # Cloudflare R2 object storage for rendered PDFs. R2 is S3-compatible:
    # ``r2_endpoint_url`` is the account endpoint
    # (https://<account>.r2.cloudflarestorage.com), and the key id/secret authenticate
    # the S3 API. Empty by default so a dev/test box needs no bucket: preview still
    # renders and streams bytes, and only export persists, which is faked in tests.
    # Delivered box-less like the other secrets.
    r2_endpoint_url: str = ""
    r2_access_key_id: SecretStr = SecretStr("")
    r2_secret_access_key: SecretStr = SecretStr("")
    r2_bucket: str = ""


class AppSettings(BaseModel):
    """Full settings for one ASGI app: shared env config plus per-app identity."""

    service: str
    port: int
    environment: str
    log_level: str
    host: str
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    internal_api_token: str = ""
    # Auth knobs, defaulted so the shared test settings factory and any non-auth
    # caller need not supply them.
    session_jwt_secret: SecretStr = SecretStr("")
    cookie_domain: str = ""
    cors_origin: str = ""
    discord_webhook_url: SecretStr = SecretStr("")
    # OAuth AS knobs, defaulted so the shared test settings factory and any
    # non-OAuth caller need not supply them.
    public_base_url: str = "http://localhost:8000"
    app_public_url: str = "http://localhost:5173"
    mcp_public_url: str = "http://localhost:9000"
    oauth_private_key_path: str = ""
    oauth_key_id: str = "floresu-oauth-dev"
    oauth_access_ttl_seconds: int = 900
    oauth_refresh_ttl_seconds: int = 2_592_000
    oauth_client_cleanup_interval_seconds: int = 21_600
    oauth_stale_client_max_age_seconds: int = 2_592_000
    # Embedding provider knobs (see EnvSettings). Defaulted so the shared test
    # settings factory and any non-embedding caller need not supply them.
    openai_api_key: SecretStr = SecretStr("")
    openai_base_url: str = "https://api.openai.com"
    # R2 object-store knobs (see EnvSettings). Defaulted so the shared test settings
    # factory and any non-rendering caller need not supply them.
    r2_endpoint_url: str = ""
    r2_access_key_id: SecretStr = SecretStr("")
    r2_secret_access_key: SecretStr = SecretStr("")
    r2_bucket: str = ""

    @property
    def is_dev(self) -> bool:
        return self.environment.lower() == "development"

    @property
    def allowed_cors_origins(self) -> list[str]:
        """Browser origins allowed to send credentialed XHRs; empty when unset."""
        return [self.cors_origin] if self.cors_origin else []


def build_app_settings(*, service: str, port: int, env: EnvSettings | None = None) -> AppSettings:
    """Compose per-app settings from injected identity and shared env config.

    Every :class:`EnvSettings` field maps 1:1 onto an :class:`AppSettings` field of
    the same name, so the env config is forwarded as one ``model_dump()`` splat
    rather than a hand-maintained field-by-field copy that drifts as knobs are
    added. The python-mode dump keeps ``SecretStr`` fields wrapped (not the plain
    value), so masking survives the round-trip; only ``service`` and ``port`` are
    the per-app identity supplied by the caller.
    """
    env = env or EnvSettings()
    return AppSettings(service=service, port=port, **env.model_dump())
