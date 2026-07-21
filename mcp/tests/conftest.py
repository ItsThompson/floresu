"""Shared MCP test fixtures."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
import structlog
from pydantic import SecretStr

from floresu_mcp.settings import SERVICE, RsSettings
from tests.token_factory import ISSUER, RESOURCE

MakeSettings = Callable[..., RsSettings]

REDIS_IMAGE = "redis:7-alpine"


@pytest.fixture(autouse=True)
def _isolate_contextvars() -> Iterator[None]:
    """Clear structlog contextvars around every test.

    The bearer boundary binds ``request_id`` / ``user_id``; clearing before and
    after keeps one test's bindings from leaking into another's assertions."""
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    """A live Redis connection URL for the rate-limiter integration test.

    Session-scoped so tests share one container. Skips automatically when
    testcontainers or Docker is unavailable, mirroring the backend fixture.
    """
    try:
        from testcontainers.redis import RedisContainer
    except ImportError:  # pragma: no cover - env without testcontainers
        pytest.skip("testcontainers not installed")

    try:
        with RedisContainer(REDIS_IMAGE) as container:
            host = container.get_container_host_ip()
            port = container.get_exposed_port(6379)
            yield f"redis://{host}:{port}/0"
    except Exception as exc:  # pragma: no cover - Docker daemon unavailable
        pytest.skip(f"Docker unavailable for integration tests: {exc}")


@pytest.fixture
def make_settings() -> MakeSettings:
    """Factory for RsSettings with production-like defaults and per-test overrides."""

    def _make(**overrides: object) -> RsSettings:
        base: dict[str, object] = {
            "service": SERVICE,
            "environment": "production",
            "log_level": "critical",
            "host": "127.0.0.1",
            "port": 9000,
            "issuer": ISSUER,
            "resource": RESOURCE,
            "backend_internal_url": "http://backend:8001",
            "internal_api_token": SecretStr("test-internal-token"),
            "redis_url": "redis://localhost:6379/0",
            "rate_limit_window_seconds": 60,
            "rate_limit_request_budget": 120,
            "rate_limit_embed_write_budget": 30,
        }
        base.update(overrides)
        return RsSettings(**base)  # type: ignore[arg-type]

    return _make
