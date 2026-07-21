"""Settings-composition tests.

``build_rs_settings`` maps the pinned env into the immutable ``RsSettings``: the
issuer/resource come from ``public_base_url`` / ``mcp_public_url`` (never a
request host), the internal token is a masked ``SecretStr``, and the CORS origin
opens only in development.
"""

from __future__ import annotations

from pydantic import SecretStr

from floresu_mcp.config import MCP_INSPECTOR_ORIGIN
from floresu_mcp.settings import SERVICE, EnvSettings, build_rs_settings


def _env(**overrides: object) -> EnvSettings:
    base: dict[str, object] = {
        "environment": "production",
        "public_base_url": "https://app.floresu.test",
        "mcp_public_url": "https://mcp.floresu.test",
        "backend_internal_url": "http://backend:8001",
        "internal_api_token": "tok-123",
    }
    base.update(overrides)
    return EnvSettings(**base)  # type: ignore[arg-type]


def test_issuer_and_resource_come_from_pinned_urls() -> None:
    settings = build_rs_settings(_env())

    assert settings.service == SERVICE
    assert settings.issuer == "https://app.floresu.test"
    assert settings.resource == "https://mcp.floresu.test"
    assert settings.backend_internal_url == "http://backend:8001"


def test_internal_token_is_a_masked_secret() -> None:
    settings = build_rs_settings(_env(internal_api_token="super-secret"))

    assert isinstance(settings.internal_api_token, SecretStr)
    assert settings.internal_api_token.get_secret_value() == "super-secret"
    # The masked repr must not leak the raw value.
    assert "super-secret" not in repr(settings.internal_api_token)


def test_cors_opens_only_in_development() -> None:
    prod = build_rs_settings(_env(environment="production"))
    dev = build_rs_settings(_env(environment="development"))

    assert prod.allowed_cors_origins == []
    assert prod.is_dev is False
    assert dev.allowed_cors_origins == [MCP_INSPECTOR_ORIGIN]
    assert dev.is_dev is True


def test_trusted_proxies_are_split_and_blanks_dropped() -> None:
    settings = build_rs_settings(_env(mcp_trusted_proxies="10.89.0.0/24, 10.89.1.1 ,"))

    assert settings.trusted_proxies == ["10.89.0.0/24", "10.89.1.1"]


def test_no_trusted_proxies_by_default() -> None:
    assert build_rs_settings(_env()).trusted_proxies == []
