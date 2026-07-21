"""Sociable tests for the SearchService orchestration.

The real service, RRF fusion, and graph assembly run over an in-memory repository
and a fake embedding provider. These cover the orchestration rules the service
owns: the empty-query and filtered-to-nothing short circuits, lexical + semantic
fusion into a scored DAG, the result limit, and the lexical-only degradation with
a soft notice when the query embedding fails.
"""

from __future__ import annotations

from datetime import date

import pytest

from floresu.core.errors import Unauthorized
from floresu.embedding.config import EmbedItemKind
from floresu.profile.models import SourceKind
from floresu.search.config import DEFAULT_SEARCH_LIMIT
from floresu.search.fusion import ItemRef
from floresu.search.schemas import SearchFilters, SearchLayer, SearchQuery
from floresu.search.service import SearchService
from tests.embedding_fakes import FakeEmbeddingProvider
from tests.search_fakes import FailingEmbeddingProvider, InMemorySearchRepository

pytestmark = pytest.mark.asyncio

_USER = "1"


def _service(repo: InMemorySearchRepository, provider: object) -> SearchService:
    return SearchService(repo, provider)  # type: ignore[arg-type]


async def test_empty_query_returns_nothing() -> None:
    repo = InMemorySearchRepository()
    repo.lexical_hits = [ItemRef(EmbedItemKind.WORKLOG, 10)]
    result = await _service(repo, FakeEmbeddingProvider()).search(_USER, SearchQuery(query="   "))
    assert result.ranked == []
    assert result.graph.worklog == []
    # A blank query never embeds or retrieves (search, not list-all).
    assert repo.semantic_vectors == []


async def test_filter_matching_no_kind_returns_empty_not_error() -> None:
    repo = InMemorySearchRepository()
    repo.lexical_hits = [ItemRef(EmbedItemKind.WORKLOG, 10)]
    # kinds keeps only sources, tags keeps only worklog: no eligible kind.
    query = SearchQuery(
        query="latency", filters=SearchFilters(kinds=[SourceKind.ROLE], tags=["python"])
    )
    result = await _service(repo, FakeEmbeddingProvider()).search(_USER, query)
    assert result.ranked == []
    assert result.graph.sources == []


async def test_fuses_lexical_and_semantic_into_a_scored_graph() -> None:
    repo = InMemorySearchRepository()
    repo.add_worklog(10, "Sharded the write path", date(2024, 3, 1))
    repo.add_bullet(20, "Cut p99 latency 40%.")
    repo.add_source(100, SourceKind.ROLE, "Staff Engineer, Acme")
    repo.corpus.worklog_source = [(10, 100)]
    repo.corpus.bullet_worklog = [(20, 10)]
    repo.lexical_hits = [ItemRef(EmbedItemKind.WORKLOG, 10), ItemRef(EmbedItemKind.BULLET, 20)]
    repo.semantic_hits = [ItemRef(EmbedItemKind.WORKLOG, 10)]

    result = await _service(repo, FakeEmbeddingProvider()).search(
        _USER, SearchQuery(query="latency")
    )

    # The worklog appears in both lists so it outranks the single-list bullet.
    assert [(hit.type, hit.id) for hit in result.ranked] == [
        (EmbedItemKind.WORKLOG, 10),
        (EmbedItemKind.BULLET, 20),
    ]
    assert [node.id for node in result.graph.worklog] == [10]
    assert [node.id for node in result.graph.bullets] == [20]
    # The source is an ancestor of the hit worklog, so it appears as a grouping
    # node with no match score of its own.
    assert [node.id for node in result.graph.sources] == [100]
    assert result.graph.sources[0].match_score is None
    assert result.notices == []


async def test_a_source_direct_hit_carries_a_match_score() -> None:
    repo = InMemorySearchRepository()
    repo.add_source(100, SourceKind.PROJECT, "Payments Platform")
    repo.lexical_hits = [ItemRef(EmbedItemKind.SOURCE, 100)]

    result = await _service(repo, FakeEmbeddingProvider()).search(
        _USER, SearchQuery(query="payments")
    )
    assert [(hit.type, hit.id) for hit in result.ranked] == [(EmbedItemKind.SOURCE, 100)]
    node = result.graph.sources[0]
    assert node.match_score is not None
    assert node.score == node.match_score


async def test_degrades_to_lexical_only_when_query_embedding_fails() -> None:
    repo = InMemorySearchRepository()
    repo.add_worklog(10, "Sharded the write path", date(2024, 3, 1))
    repo.lexical_hits = [ItemRef(EmbedItemKind.WORKLOG, 10)]
    repo.semantic_hits = [ItemRef(EmbedItemKind.WORKLOG, 10)]

    result = await _service(repo, FailingEmbeddingProvider()).search(
        _USER, SearchQuery(query="latency")
    )
    # Lexical hit still returned; the semantic retriever was never reached.
    assert [hit.id for hit in result.ranked] == [10]
    assert repo.semantic_vectors == []
    assert [notice.code for notice in result.notices] == ["semantic_unavailable"]


async def test_result_is_truncated_to_the_limit() -> None:
    repo = InMemorySearchRepository()
    for worklog_id in range(1, 6):
        repo.add_worklog(worklog_id, f"entry {worklog_id}", date(2024, 1, worklog_id))
    repo.lexical_hits = [ItemRef(EmbedItemKind.WORKLOG, worklog_id) for worklog_id in range(1, 6)]

    query = SearchQuery(query="entry", filters=SearchFilters(limit=2))
    result = await _service(repo, FakeEmbeddingProvider()).search(_USER, query)
    assert len(result.ranked) == 2
    assert len(result.graph.worklog) == 2


async def test_library_layer_searches_only_bullets() -> None:
    repo = InMemorySearchRepository()
    repo.add_worklog(10, "Sharded the write path", date(2024, 3, 1))
    repo.add_bullet(20, "Cut p99 latency 40%.")
    repo.lexical_hits = [ItemRef(EmbedItemKind.WORKLOG, 10), ItemRef(EmbedItemKind.BULLET, 20)]

    query = SearchQuery(query="latency", filters=SearchFilters(layer=SearchLayer.LIBRARY))
    result = await _service(repo, FakeEmbeddingProvider()).search(_USER, query)
    assert [(hit.type, hit.id) for hit in result.ranked] == [(EmbedItemKind.BULLET, 20)]


async def test_default_limit_is_applied_when_unset() -> None:
    repo = InMemorySearchRepository()
    assert DEFAULT_SEARCH_LIMIT >= 1  # the service resolves None to this default
    repo.lexical_hits = [ItemRef(EmbedItemKind.WORKLOG, 10)]
    repo.add_worklog(10, "entry", date(2024, 1, 1))
    result = await _service(repo, FakeEmbeddingProvider()).search(_USER, SearchQuery(query="x"))
    assert [hit.id for hit in result.ranked] == [10]


async def test_a_non_numeric_identity_is_rejected() -> None:
    repo = InMemorySearchRepository()
    with pytest.raises(Unauthorized):
        await _service(repo, FakeEmbeddingProvider()).search("not-a-pk", SearchQuery(query="x"))
