"""Contract tests for the internal /embed/items routes (the worker's hop).

Drives the real router and :class:`EmbeddingService` through ``TestClient`` with
the in-memory repository, a seeded fake corpus, and a fake provider substituted
for Postgres/OpenAI. Asserts the read/store/delete flow, the gate outcomes echoed
as the store status, the 404 for a missing item, and that the routes require the
internal token. No database is required.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from fastapi import Request
from fastapi.testclient import TestClient

from floresu.core.app_factory import create_app
from floresu.core.errors import build_exception_handlers
from floresu.core.headers import ACTOR_HEADER, INTERNAL_API_TOKEN_HEADER, USER_ID_HEADER
from floresu.core.identity import require_internal_user
from floresu.core.settings import AppSettings
from floresu.embedding.config import EMBEDDING_DIMENSION, EmbedItemKind
from floresu.embedding.router import create_embedding_router
from floresu.embedding.service import EmbeddingService
from tests.embedding_fakes import (
    FakeCorpusResolver,
    FakeEmbeddingProvider,
    InMemoryEmbeddingRepository,
    corpus_item,
)
from tests.support.fakes import FakeSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

MakeSettings = Callable[..., AppSettings]

_INTERNAL_TOKEN = "internal-secret"
_HEADERS = {
    INTERNAL_API_TOKEN_HEADER: _INTERNAL_TOKEN,
    USER_ID_HEADER: "1",
    ACTOR_HEADER: "floresu-embed-worker",
}


def _client(
    make_settings: MakeSettings,
) -> tuple[TestClient, InMemoryEmbeddingRepository, FakeCorpusResolver]:
    repo = InMemoryEmbeddingRepository()
    resolver = FakeCorpusResolver()
    provider = FakeEmbeddingProvider()

    def provide(_request: Request) -> EmbeddingService:
        return EmbeddingService(cast("AsyncSession", FakeSession()), repo, resolver, provider)

    router = create_embedding_router(provide, identity=require_internal_user)
    settings = make_settings(service="floresu-internal", internal_api_token=_INTERNAL_TOKEN)
    app = create_app(settings, routers=[router], exception_handlers=build_exception_handlers())
    return TestClient(app), repo, resolver


def test_read_item_returns_the_corpus_content(make_settings: MakeSettings) -> None:
    client, _repo, resolver = _client(make_settings)
    resolver.seed(EmbedItemKind.WORKLOG, 5, corpus_item("shipped it", "h1"))

    response = client.get("/embed/items/worklog/5", headers=_HEADERS)

    assert response.status_code == 200
    assert response.json() == {"text": "shipped it", "content_hash": "h1", "archived": False}


def test_read_missing_item_is_404(make_settings: MakeSettings) -> None:
    client, _repo, _resolver = _client(make_settings)
    response = client.get("/embed/items/worklog/404", headers=_HEADERS)
    assert response.status_code == 404


def test_store_vector_applies_and_reports_status(make_settings: MakeSettings) -> None:
    client, _repo, resolver = _client(make_settings)
    resolver.seed(EmbedItemKind.BULLET, 9, corpus_item("text", "h1"))

    response = client.put(
        "/embed/items/bullet/9",
        headers=_HEADERS,
        json={"content_hash": "h1", "vector": [0.1] * EMBEDDING_DIMENSION, "model": "worker-model"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "applied"}


def test_store_vector_superseded_is_reported(make_settings: MakeSettings) -> None:
    client, _repo, resolver = _client(make_settings)
    resolver.seed(EmbedItemKind.BULLET, 9, corpus_item("text", "h2"))

    response = client.put(
        "/embed/items/bullet/9",
        headers=_HEADERS,
        json={"content_hash": "h1", "vector": [0.1] * EMBEDDING_DIMENSION, "model": "m"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "superseded"}


def test_store_vector_rejects_a_wrong_width_vector(make_settings: MakeSettings) -> None:
    client, _repo, resolver = _client(make_settings)
    resolver.seed(EmbedItemKind.BULLET, 9, corpus_item("text", "h1"))

    response = client.put(
        "/embed/items/bullet/9",
        headers=_HEADERS,
        json={"content_hash": "h1", "vector": [0.1, 0.2], "model": "m"},
    )

    assert response.status_code == 422  # dimension-pinned schema rejects the short vector


def test_purge_vector_returns_204(make_settings: MakeSettings) -> None:
    client, _repo, _resolver = _client(make_settings)
    response = client.post("/embed/items/worklog/5/purge", headers=_HEADERS)
    assert response.status_code == 204


def test_routes_require_the_internal_token(make_settings: MakeSettings) -> None:
    client, _repo, _resolver = _client(make_settings)
    response = client.get("/embed/items/worklog/5", headers={USER_ID_HEADER: "1"})
    assert response.status_code == 401


def test_unknown_kind_is_rejected(make_settings: MakeSettings) -> None:
    client, _repo, _resolver = _client(make_settings)
    response = client.get("/embed/items/resume/5", headers=_HEADERS)
    assert response.status_code == 422  # not a member of embed_item_kind


def test_read_item_with_a_malformed_identity_is_401(make_settings: MakeSettings) -> None:
    client, _repo, resolver = _client(make_settings)
    resolver.seed(EmbedItemKind.WORKLOG, 5, corpus_item("shipped it", "h1"))

    response = client.get(
        "/embed/items/worklog/5", headers={**_HEADERS, USER_ID_HEADER: "not-a-pk"}
    )

    assert response.status_code == 401  # the service casts and rejects the bad id


def test_purge_with_a_malformed_identity_is_401(make_settings: MakeSettings) -> None:
    client, _repo, _resolver = _client(make_settings)

    response = client.post(
        "/embed/items/worklog/5/purge", headers={**_HEADERS, USER_ID_HEADER: "not-a-pk"}
    )

    assert response.status_code == 401
