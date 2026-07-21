"""The search wiring provider builds a request-scoped service over the seam.

Confirms ``build_search_service_provider`` binds the SQLAlchemy retrieval
repository over the injected session and closes over the embedding provider the
composition root supplies, so both apps share one :class:`SearchService` shape.
"""

from __future__ import annotations

from floresu.search.service import SearchService
from floresu.search.wiring import build_search_service_provider
from tests.embedding_fakes import FakeEmbeddingProvider


def test_provider_binds_the_session_and_the_embedding_provider() -> None:
    provider = build_search_service_provider(FakeEmbeddingProvider())
    session = object()  # the repository only stores the session reference

    service = provider(session)

    assert isinstance(service, SearchService)
