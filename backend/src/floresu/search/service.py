"""SearchService: the one home for the retrieve → fuse → assemble-graph flow.

The single public entry point resolves the query, retrieves lexically and (best
effort) semantically, fuses the two rankings with RRF, then loads the hit set's
provenance edges and rolls the hits into the scored DAG. It owns two soft-failure
rules the acceptance criteria require:

- an empty query (or one filtered down to no eligible kinds) returns an empty
  result, never a full dump and never an error;
- a failed query embedding degrades to lexical-only and surfaces a soft notice
  rather than failing the whole query.

Retrieval, fusion, and graph assembly are separate, independently tested pieces
(the SQL in :mod:`floresu.search.retrieval`; the pure RRF in
:mod:`floresu.search.fusion`; the pure DAG in :mod:`floresu.search.graph`); this
service is the thin orchestration that sequences them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.core.identity import resolve_user_pk
from floresu.core.logging import get_logger
from floresu.core.observability import track_failures
from floresu.embedding.config import EmbedItemKind
from floresu.search.config import candidate_pool, resolve_limit
from floresu.search.eligibility import eligible_kinds
from floresu.search.fusion import FusedHit, ItemRef, reciprocal_rank_fusion
from floresu.search.graph import assemble_graph
from floresu.search.schemas import (
    SEMANTIC_UNAVAILABLE,
    RankedHit,
    SearchFilters,
    SearchGraph,
    SearchNotice,
    SearchQuery,
    SearchResult,
    empty_result,
)

if TYPE_CHECKING:
    from floresu.embedding.provider import EmbeddingProvider
    from floresu.search.retrieval import SearchRepository

_log = get_logger("floresu-search")


@track_failures("search")
class SearchService:
    """Run a hybrid search: lexical + semantic retrieval, RRF fusion, scored DAG."""

    def __init__(self, repo: SearchRepository, provider: EmbeddingProvider) -> None:
        self._repo = repo
        self._provider = provider

    async def search(self, user_id: str, query: SearchQuery) -> SearchResult:
        """Retrieve, fuse, and assemble the scored provenance DAG for one query."""
        pk = resolve_user_pk(user_id)
        terms = query.query.strip()
        eligible = eligible_kinds(query.filters)
        # Search, not list-all: a blank query returns nothing; a filter set that
        # leaves no eligible kind returns an empty result, not an error.
        if not terms or not eligible:
            return empty_result()

        limit = resolve_limit(query.filters.limit)
        pool = candidate_pool(limit)
        lexical = await self._repo.lexical(pk, terms, query.filters, eligible, pool)
        semantic, notices = await self._semantic(pk, terms, query.filters, eligible, pool)

        fused = reciprocal_rank_fusion([lexical, semantic])[:limit]
        if not fused:
            return empty_result(notices)
        graph = await self._assemble(pk, fused)
        ranked = [
            RankedHit(type=hit.ref.kind, id=hit.ref.item_id, score=hit.score) for hit in fused
        ]
        return SearchResult(ranked=ranked, graph=graph, notices=notices)

    async def _semantic(
        self,
        user_id: int,
        terms: str,
        filters: SearchFilters,
        eligible: frozenset[EmbedItemKind],
        pool: int,
    ) -> tuple[list[ItemRef], list[SearchNotice]]:
        """Embed the query and retrieve semantically; degrade to lexical-only on failure.

        A provider outage (or an unconfigured provider) must not fail the query, so
        an embedding failure is caught, logged, and turned into a soft notice while
        the lexical results still stand.
        """
        try:
            vectors = await self._provider.embed([terms])
        except Exception as exc:  # provider outage / network / unconfigured key
            _log.warning("search_semantic_degraded", error=str(exc))
            return [], [SEMANTIC_UNAVAILABLE]
        semantic = await self._repo.semantic(user_id, vectors[0], filters, eligible, pool)
        return semantic, []

    async def _assemble(self, user_id: int, fused: list[FusedHit]) -> SearchGraph:
        worklog_ids = {hit.ref.item_id for hit in fused if hit.ref.kind is EmbedItemKind.WORKLOG}
        bullet_ids = {hit.ref.item_id for hit in fused if hit.ref.kind is EmbedItemKind.BULLET}
        source_ids = {hit.ref.item_id for hit in fused if hit.ref.kind is EmbedItemKind.SOURCE}
        inputs = await self._repo.graph_inputs(user_id, worklog_ids, bullet_ids, source_ids)
        return assemble_graph(
            fused,
            source_meta=inputs.source_meta,
            worklog_meta=inputs.worklog_meta,
            bullet_meta=inputs.bullet_meta,
            bullet_worklog_edges=inputs.bullet_worklog_edges,
            bullet_source_edges=inputs.bullet_source_edges,
            worklog_source_edges=inputs.worklog_source_edges,
        )
