"""Settings: shared env config plus per-app injected identity."""

from __future__ import annotations

import pytest

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
