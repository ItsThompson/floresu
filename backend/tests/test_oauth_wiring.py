"""Unit tests for the OAuth wiring seam (request-scoped service composition)."""

from __future__ import annotations

import pytest

from floresu.core.db import create_database
from floresu.oauth.authorization import AuthorizationService
from floresu.oauth.token_exchange import TokenService
from floresu.oauth.wiring import (
    build_authorization_service_provider,
    build_token_service,
    build_token_service_provider,
)
from tests.oauth_fakes import build_test_codec, build_test_config, build_test_keyset

# A syntactically valid async URL; the engine connects lazily, so composing a
# service over a session never touches a database.
_URL = "postgresql+asyncpg://floresu:floresu@localhost:5432/floresu"


async def test_authorization_provider_builds_a_request_scoped_service() -> None:
    config = build_test_config()
    provider = build_authorization_service_provider(config)
    database = create_database(_URL)
    try:
        async with database.sessionmaker() as session:
            service = provider(session)
        assert isinstance(service, AuthorizationService)
    finally:
        await database.engine.dispose()


async def test_token_provider_and_builder_agree_on_composition() -> None:
    config = build_test_config()
    codec = build_test_codec(config, build_test_keyset(config))
    provider = build_token_service_provider(config, codec)
    database = create_database(_URL)
    try:
        async with database.sessionmaker() as session:
            from_provider = provider(session)
            from_builder = build_token_service(session, config, codec)
        assert isinstance(from_provider, TokenService)
        assert isinstance(from_builder, TokenService)
    finally:
        await database.engine.dispose()


@pytest.mark.parametrize("provider_factory", ["auth", "token"])
async def test_providers_are_reusable_across_requests(provider_factory: str) -> None:
    config = build_test_config()
    codec = build_test_codec(config, build_test_keyset(config))
    provider = (
        build_authorization_service_provider(config)
        if provider_factory == "auth"
        else build_token_service_provider(config, codec)
    )
    database = create_database(_URL)
    try:
        async with database.sessionmaker() as first, database.sessionmaker() as second:
            # Each request gets its own service instance over its own session.
            assert provider(first) is not provider(second)
    finally:
        await database.engine.dispose()
