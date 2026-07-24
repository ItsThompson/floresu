"""Compose the embedding pipeline's dependencies for both apps and the worker hop.

Three composition seams, kept out of the routers and entrypoints:

- :func:`build_embedding_service_provider` is the request-scoped
  :class:`EmbeddingService` the internal app's worker-facing routes depend on. It
  binds the repository over the request session and reuses the process-wide
  resolver and provider.
- :func:`create_embedding_provider` builds the one OpenAI provider from settings
  (an injected ``httpx.AsyncClient`` bound to the API with the bearer set); a fake
  is injected in tests instead.
- :func:`build_embed_queue` builds the arq queue the external app enqueues onto.

The two post-commit consumers (:func:`build_async_embed_enqueue_consumer` and
:func:`build_sync_embed_fastpath_consumer`) live in :mod:`floresu.embedding.enqueue`
and are registered at each composition root: the external/web app enqueues
(asynchronous, worker-drained), the internal/agent app embeds inline (fast-path).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from floresu.core.providers import ServiceProvider, session_provider
from floresu.embedding.corpus import CorpusResolver
from floresu.embedding.provider import OpenAIEmbeddingProvider
from floresu.embedding.queue import ArqEmbedQueue, create_arq_pool
from floresu.embedding.repository import SqlAlchemyEmbeddingRepository
from floresu.embedding.service import EmbeddingService

if TYPE_CHECKING:
    from floresu.core.settings import AppSettings
    from floresu.embedding.provider import EmbeddingProvider

# The resolver is stateless, so one instance is shared across requests.
_RESOLVER = CorpusResolver()

# Bound so a hung provider call cannot pin a request or a worker indefinitely.
_PROVIDER_TIMEOUT_SECONDS = 30.0


def create_openai_http_client(settings: AppSettings) -> httpx.AsyncClient:
    """Build the ``httpx.AsyncClient`` bound to the OpenAI API with the bearer set."""
    return httpx.AsyncClient(
        base_url=settings.openai_base_url,
        headers={"Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}"},
        timeout=_PROVIDER_TIMEOUT_SECONDS,
    )


def create_embedding_provider(http_client: httpx.AsyncClient) -> OpenAIEmbeddingProvider:
    """Build the P0 OpenAI provider over the given client (pinned model + dimension)."""
    return OpenAIEmbeddingProvider(http_client)


def build_embedding_service_provider(
    provider: EmbeddingProvider,
) -> ServiceProvider[EmbeddingService]:
    """A FastAPI dependency that builds a request-scoped :class:`EmbeddingService`."""
    return session_provider(
        lambda session: EmbeddingService(
            session, SqlAlchemyEmbeddingRepository(session), _RESOLVER, provider
        )
    )


def build_embed_queue(redis_url: str) -> ArqEmbedQueue:
    """Build the arq-backed embed queue the external app enqueues onto (lazy pool)."""
    return ArqEmbedQueue(create_arq_pool(redis_url))


def embedding_resolver() -> CorpusResolver:
    """The shared stateless corpus resolver, for the fast-path consumer wiring."""
    return _RESOLVER
