"""Unit tests for the embedding composition seams.

Verify the OpenAI client is bound to the configured base URL with the bearer set,
the provider is the pinned P0 model, the arq queue is built, and the request-scoped
service provider builds an :class:`EmbeddingService` over the given session.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.core.settings import build_app_settings
from floresu.embedding.config import EMBEDDING_DIMENSION, EMBEDDING_MODEL
from floresu.embedding.provider import OpenAIEmbeddingProvider
from floresu.embedding.queue import ArqEmbedQueue
from floresu.embedding.service import EmbeddingService
from floresu.embedding.wiring import (
    build_embed_queue,
    build_embedding_service_provider,
    create_embedding_provider,
    create_openai_http_client,
)
from tests.embedding_fakes import FakeEmbeddingProvider
from tests.support.fakes import FakeSession

if TYPE_CHECKING:
    from floresu.core.settings import EnvSettings


def _settings(**overrides: object) -> object:
    env: EnvSettings | None = None
    from floresu.core.settings import EnvSettings as _Env

    env = _Env(
        openai_api_key="sk-test-key",  # type: ignore[arg-type]
        openai_base_url="https://api.openai.test",
        **overrides,  # type: ignore[arg-type]
    )
    return build_app_settings(service="t", port=1, env=env)


async def test_openai_client_is_bound_to_base_url_with_bearer() -> None:
    client = create_openai_http_client(_settings())  # type: ignore[arg-type]
    try:
        assert str(client.base_url) == "https://api.openai.test"
        assert client.headers["Authorization"] == "Bearer sk-test-key"
    finally:
        await client.aclose()


async def test_create_embedding_provider_is_the_pinned_p0_model() -> None:
    client = create_openai_http_client(_settings())  # type: ignore[arg-type]
    try:
        provider = create_embedding_provider(client)
        assert isinstance(provider, OpenAIEmbeddingProvider)
        assert provider.model == EMBEDDING_MODEL
        assert provider.dimension == EMBEDDING_DIMENSION
    finally:
        await client.aclose()


def test_build_embed_queue_returns_an_arq_queue() -> None:
    queue = build_embed_queue("redis://localhost:6379/0")
    assert isinstance(queue, ArqEmbedQueue)


def test_service_provider_builds_a_service_over_the_session() -> None:
    provider = FakeEmbeddingProvider()
    build = build_embedding_service_provider(provider)
    service = build(session=FakeSession())
    assert isinstance(service, EmbeddingService)
