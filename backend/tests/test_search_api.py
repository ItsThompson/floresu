"""End-to-end contract tests for the /search surface on both app shapes.

Drives the real router and service through ``TestClient`` with the in-memory
repository and a fake embedding provider substituted for Postgres and OpenAI.
Asserts the request/response shape (ranked list + scored provenance graph), the
soft degradation notice, and that both the external (cookie) and internal
(trusted-header) boundaries resolve the identity and reach the service. No
database is required.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from fastapi.testclient import TestClient

from floresu.core.app_factory import create_app
from floresu.core.errors import build_exception_handlers
from floresu.core.headers import INTERNAL_API_TOKEN_HEADER, USER_ID_HEADER
from floresu.core.identity import SESSION_COOKIE_NAME, require_internal_user, require_user
from floresu.core.settings import AppSettings
from floresu.embedding.config import EmbedItemKind
from floresu.profile.models import SourceKind
from floresu.search.fusion import ItemRef
from floresu.search.router import create_search_router
from floresu.search.service import SearchService
from tests.embedding_fakes import FakeEmbeddingProvider
from tests.search_fakes import FailingEmbeddingProvider, InMemorySearchRepository

MakeSettings = Callable[..., AppSettings]

_INTERNAL_TOKEN = "internal-secret"
_INTERNAL_HEADERS = {INTERNAL_API_TOKEN_HEADER: _INTERNAL_TOKEN, USER_ID_HEADER: "1"}


def _client(
    make_settings: MakeSettings, *, internal: bool, provider: object | None = None
) -> tuple[TestClient, InMemorySearchRepository]:
    repo = InMemorySearchRepository()
    embed_provider = provider or FakeEmbeddingProvider()

    def service_provider() -> SearchService:
        return SearchService(repo, embed_provider)  # type: ignore[arg-type]

    if internal:
        router = create_search_router(service_provider, identity=require_internal_user)
        settings = make_settings(service="floresu-internal", internal_api_token=_INTERNAL_TOKEN)
    else:
        router = create_search_router(service_provider, identity=require_user)
        settings = make_settings(service="floresu-external", environment="development")

    app = create_app(settings, routers=[router], exception_handlers=build_exception_handlers())

    async def verify(_cookie: str) -> str:
        return "1"

    app.state.session_verifier = verify
    client = TestClient(app)
    if not internal:
        client.cookies.set(SESSION_COOKIE_NAME, "session-token")
    return client, repo


def _seed(repo: InMemorySearchRepository) -> None:
    repo.add_worklog(10, "Sharded the write path", date(2024, 3, 1))
    repo.add_bullet(20, "Cut p99 latency 40%.")
    repo.add_source(100, SourceKind.ROLE, "Staff Engineer, Acme")
    repo.corpus.worklog_source = [(10, 100)]
    repo.corpus.bullet_worklog = [(20, 10)]
    repo.lexical_hits = [ItemRef(EmbedItemKind.WORKLOG, 10), ItemRef(EmbedItemKind.BULLET, 20)]
    repo.semantic_hits = [ItemRef(EmbedItemKind.WORKLOG, 10)]


def test_search_returns_ranked_list_and_scored_graph(make_settings: MakeSettings) -> None:
    client, repo = _client(make_settings, internal=False)
    _seed(repo)

    response = client.post("/search", json={"query": "latency"})
    assert response.status_code == 200
    body = response.json()
    assert [[hit["type"], hit["id"]] for hit in body["ranked"]] == [
        ["worklog", 10],
        ["bullet", 20],
    ]
    assert [node["id"] for node in body["graph"]["worklog"]] == [10]
    assert [node["id"] for node in body["graph"]["bullets"]] == [20]
    assert [node["id"] for node in body["graph"]["sources"]] == [100]
    assert body["graph"]["sources"][0]["match_score"] is None
    assert body["notices"] == []


def test_empty_query_returns_empty_result(make_settings: MakeSettings) -> None:
    client, repo = _client(make_settings, internal=False)
    _seed(repo)
    response = client.post("/search", json={"query": ""})
    assert response.status_code == 200
    body = response.json()
    assert body["ranked"] == []
    assert body["graph"] == {"sources": [], "worklog": [], "bullets": []}


def test_filters_are_accepted_and_narrow_the_search(make_settings: MakeSettings) -> None:
    client, repo = _client(make_settings, internal=False)
    _seed(repo)
    # layer=library keeps only the bullet hit.
    response = client.post("/search", json={"query": "latency", "filters": {"layer": "library"}})
    assert response.status_code == 200
    assert [[hit["type"], hit["id"]] for hit in response.json()["ranked"]] == [["bullet", 20]]


def test_date_range_filter_uses_from_and_to_wire_names(make_settings: MakeSettings) -> None:
    client, repo = _client(make_settings, internal=False)
    _seed(repo)
    response = client.post(
        "/search",
        json={
            "query": "latency",
            "filters": {"date_range": {"from": "2024-01-01", "to": "2024-12-31"}},
        },
    )
    assert response.status_code == 200


def test_degraded_semantic_surfaces_a_soft_notice(make_settings: MakeSettings) -> None:
    client, repo = _client(make_settings, internal=False, provider=FailingEmbeddingProvider())
    _seed(repo)
    response = client.post("/search", json={"query": "latency"})
    assert response.status_code == 200
    assert [notice["code"] for notice in response.json()["notices"]] == ["semantic_unavailable"]


def test_unauthenticated_search_is_rejected(make_settings: MakeSettings) -> None:
    client, _ = _client(make_settings, internal=False)
    client.cookies.clear()
    assert client.post("/search", json={"query": "latency"}).status_code == 401


def test_internal_boundary_resolves_the_trusted_identity(make_settings: MakeSettings) -> None:
    client, repo = _client(make_settings, internal=True)
    _seed(repo)
    response = client.post("/search", json={"query": "latency"}, headers=_INTERNAL_HEADERS)
    assert response.status_code == 200
    assert [hit["id"] for hit in response.json()["ranked"]] == [10, 20]


def test_internal_boundary_rejects_a_missing_token(make_settings: MakeSettings) -> None:
    client, _ = _client(make_settings, internal=True)
    response = client.post("/search", json={"query": "latency"}, headers={USER_ID_HEADER: "1"})
    assert response.status_code == 401
