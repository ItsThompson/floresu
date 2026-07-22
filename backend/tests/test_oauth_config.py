"""Unit tests for the OAuth config: pinned URLs and canonical-resource resolution."""

from __future__ import annotations

from datetime import timedelta

from floresu.core.settings import AppSettings
from floresu.oauth.config import (
    AUTHORIZE_PATH,
    SCOPE_FULL,
    SUPPORTED_SCOPES,
    TOKEN_PATH,
    build_oauth_config,
)
from tests.oauth_fakes import build_test_config


def test_endpoint_urls_are_built_from_the_pinned_issuer() -> None:
    config = build_test_config()
    assert config.endpoint(TOKEN_PATH) == "https://api.floresu.com/oauth/token"
    assert config.endpoint(AUTHORIZE_PATH) == "https://api.floresu.com/oauth/authorize"


def test_consent_url_is_the_pinned_spa_origin() -> None:
    config = build_test_config()
    assert config.consent_url == "https://floresu.com/authorize"


def test_single_full_scope_is_the_only_supported_scope() -> None:
    assert SUPPORTED_SCOPES == (SCOPE_FULL,)


def test_canonical_resource_defaults_missing_to_the_mcp_resource() -> None:
    config = build_test_config()
    assert config.canonical_resource(None) == config.resource
    assert config.canonical_resource("") == config.resource


def test_canonical_resource_matches_ignoring_trailing_slash() -> None:
    config = build_test_config()
    assert config.canonical_resource("https://mcp.floresu.com/") == config.resource


def test_canonical_resource_rejects_a_foreign_audience() -> None:
    config = build_test_config()
    assert config.canonical_resource("https://evil.example") is None


def test_build_oauth_config_reads_pinned_settings() -> None:
    settings = AppSettings(
        service="floresu-external",
        port=8000,
        environment="production",
        log_level="info",
        host="0.0.0.0",
        database_url="postgresql+asyncpg://floresu:floresu@localhost:5432/floresu",
        public_base_url="https://api.floresu.com",
        app_public_url="https://floresu.com",
        mcp_public_url="https://mcp.floresu.com",
        oauth_key_id="prod-kid",
        oauth_access_ttl_seconds=600,
        oauth_refresh_ttl_seconds=1200,
    )
    config = build_oauth_config(settings)
    assert config.issuer == "https://api.floresu.com"
    assert config.consent_base_url == "https://floresu.com"
    assert config.resource == "https://mcp.floresu.com"
    assert config.key_id == "prod-kid"
    assert config.access_ttl == timedelta(seconds=600)
    assert config.refresh_ttl == timedelta(seconds=1200)
