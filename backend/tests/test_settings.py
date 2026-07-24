"""Settings: shared env config plus per-app injected identity."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from floresu.core.settings import (
    EXTERNAL_PORT,
    EXTERNAL_SERVICE,
    INTERNAL_PORT,
    INTERNAL_SERVICE,
    EnvSettings,
    build_app_settings,
)


def test_build_app_settings_injects_per_app_identity() -> None:
    env = EnvSettings(
        environment="production",
        log_level="warning",
        database_url="postgresql+asyncpg://u:p@db:5432/floresu",
    )
    external = build_app_settings(service=EXTERNAL_SERVICE, port=EXTERNAL_PORT, env=env)
    internal = build_app_settings(service=INTERNAL_SERVICE, port=INTERNAL_PORT, env=env)

    # Both apps share every env-sourced field and differ only by identity.
    assert external.service == "floresu-external"
    assert external.port == 8000
    assert internal.service == "floresu-internal"
    assert internal.port == 8001
    assert (
        external.database_url == internal.database_url == "postgresql+asyncpg://u:p@db:5432/floresu"
    )
    assert external.log_level == internal.log_level == "warning"


def test_build_app_settings_forwards_every_env_field_unchanged() -> None:
    # Distinct non-default values for all 24 env fields prove build_app_settings
    # forwards each one 1:1 (including the SecretStr fields) rather than dropping,
    # renaming, or crossing any as the model_dump() splat is applied.
    env = EnvSettings(
        environment="production",
        log_level="warning",
        host="127.0.0.1",
        database_url="postgresql+asyncpg://u:p@db:5432/floresu",
        redis_url="redis://cache:6380/2",
        internal_api_token="internal-token",
        session_jwt_secret=SecretStr("session-secret"),
        cookie_domain="floresu.example",
        cors_origin="https://app.floresu.example",
        public_base_url="https://api.floresu.example",
        app_public_url="https://app.floresu.example",
        mcp_public_url="https://mcp.floresu.example",
        oauth_private_key_path="/etc/floresu/oauth.pem",
        oauth_key_id="floresu-oauth-prod",
        oauth_access_ttl_seconds=1200,
        oauth_refresh_ttl_seconds=1_000_000,
        oauth_client_cleanup_interval_seconds=3600,
        oauth_stale_client_max_age_seconds=5_000_000,
        openai_api_key=SecretStr("openai-key"),
        openai_base_url="https://proxy.floresu.example",
        r2_endpoint_url="https://acct.r2.cloudflarestorage.com",
        r2_access_key_id=SecretStr("r2-access"),
        r2_secret_access_key=SecretStr("r2-secret"),
        r2_bucket="floresu-pdfs",
    )
    dumped = env.model_dump()
    assert len(dumped) == 24

    app = build_app_settings(service=EXTERNAL_SERVICE, port=EXTERNAL_PORT, env=env)

    for name, expected in dumped.items():
        actual = getattr(app, name)
        if isinstance(expected, SecretStr):
            # SecretStr masks its repr; confirm the field stayed wrapped and its
            # unwrapped value survived the python-mode model_dump round-trip.
            assert isinstance(actual, SecretStr)
            assert actual.get_secret_value() == expected.get_secret_value()
        else:
            assert actual == expected


def test_is_dev_reflects_environment() -> None:
    env = build_app_settings(service="s", port=1, env=EnvSettings(environment="development"))
    prod = build_app_settings(service="s", port=1, env=EnvSettings(environment="production"))
    assert env.is_dev is True
    assert prod.is_dev is False


def test_defaults_target_the_local_dev_stack(monkeypatch: pytest.MonkeyPatch) -> None:
    # With no env overrides the DB URL points at the docker-compose Postgres and
    # the environment is development, so the host inner loop needs no config.
    for key in ("ENVIRONMENT", "LOG_LEVEL", "HOST", "DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    env = EnvSettings()
    assert env.environment == "development"
    assert env.database_url.startswith("postgresql+asyncpg://")
    assert ":5432/floresu" in env.database_url
