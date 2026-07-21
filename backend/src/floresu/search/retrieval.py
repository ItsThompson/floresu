"""Retrieval over the corpus: lexical FTS and semantic pgvector ANN.

The service depends on the :class:`SearchRepository` interface and receives a
concrete binding, so tests substitute an in-memory double at the one true external
boundary (Postgres) while production binds :class:`SqlAlchemySearchRepository`.

Two retrievers run per eligible kind and each returns a best-first list of
:class:`~floresu.search.fusion.ItemRef`:

- **lexical** matches the :mod:`~floresu.search.predicates` ``to_tsvector``
  documents against ``websearch_to_tsquery`` and ranks by ``ts_rank_cd`` (the same
  GIN-indexed expressions migration 0011 built);
- **semantic** orders the item's stored vector by cosine distance to the query
  vector (the HNSW-indexed ``embeddings`` table).

Every retrieval is scoped to the owner and ``archived_at IS NULL`` and applies the
per-kind filter predicates from :mod:`floresu.search.predicates`, so an archived
item and a filtered-out item never enter the ranking. The hit-set graph inputs
(node metadata + the three provenance joins) are loaded by
:func:`floresu.search.graph_inputs.load_graph_inputs`; :class:`GraphInputs` is
re-exported here so callers depend on the one retrieval seam.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sqlalchemy import ColumnElement, func, or_, select

from floresu.embedding.config import EmbedItemKind
from floresu.embedding.models import Embedding
from floresu.library.models import Bulletpoint
from floresu.profile.models import Role, Source
from floresu.search.fusion import ItemRef
from floresu.search.graph_inputs import GraphInputs, load_graph_inputs
from floresu.search.predicates import (
    BULLET_DOC,
    REGCONFIG,
    ROLE_DOC,
    SOURCE_DOC,
    WORKLOG_DOC,
    bullet_predicates,
    source_predicates,
    worklog_predicates,
)
from floresu.worklog.models import WorklogEntry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.search.schemas import SearchFilters

__all__ = ["GraphInputs", "SearchRepository", "SqlAlchemySearchRepository"]


class SearchRepository(Protocol):
    """Corpus retrieval and hit-set graph loading the search service depends on."""

    async def lexical(
        self,
        user_id: int,
        query: str,
        filters: SearchFilters,
        eligible: frozenset[EmbedItemKind],
        limit: int,
    ) -> list[ItemRef]:
        """Best-first lexical (FTS) hits across the eligible kinds."""
        ...

    async def semantic(
        self,
        user_id: int,
        query_vector: list[float],
        filters: SearchFilters,
        eligible: frozenset[EmbedItemKind],
        limit: int,
    ) -> list[ItemRef]:
        """Best-first semantic (cosine ANN) hits across the eligible kinds."""
        ...

    async def graph_inputs(
        self,
        user_id: int,
        worklog_ids: set[int],
        bullet_ids: set[int],
        source_ids: set[int],
    ) -> GraphInputs:
        """Node metadata and provenance edges for a hit set (owner-scoped)."""
        ...


class SqlAlchemySearchRepository:
    """The Postgres-backed :class:`SearchRepository`, bound over a request session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lexical(
        self,
        user_id: int,
        query: str,
        filters: SearchFilters,
        eligible: frozenset[EmbedItemKind],
        limit: int,
    ) -> list[ItemRef]:
        tsquery = func.websearch_to_tsquery(REGCONFIG, query)
        scored: list[tuple[ItemRef, float]] = []
        if EmbedItemKind.WORKLOG in eligible:
            scored += await self._lexical_worklog(user_id, tsquery, filters, limit)
        if EmbedItemKind.SOURCE in eligible:
            scored += await self._lexical_source(user_id, tsquery, filters, limit)
        if EmbedItemKind.BULLET in eligible:
            scored += await self._lexical_bullet(user_id, tsquery, filters, limit)
        # Merge across kinds by descending relevance; ts_rank_cd is comparable
        # across kinds (same function, same query).
        scored.sort(key=lambda item: -item[1])
        return [ref for ref, _score in scored]

    async def semantic(
        self,
        user_id: int,
        query_vector: list[float],
        filters: SearchFilters,
        eligible: frozenset[EmbedItemKind],
        limit: int,
    ) -> list[ItemRef]:
        distance = Embedding.vector.cosine_distance(query_vector)
        scored: list[tuple[ItemRef, float]] = []
        if EmbedItemKind.WORKLOG in eligible:
            scored += await self._semantic_kind(
                user_id, EmbedItemKind.WORKLOG, WorklogEntry, distance, filters, limit
            )
        if EmbedItemKind.SOURCE in eligible:
            scored += await self._semantic_kind(
                user_id, EmbedItemKind.SOURCE, Source, distance, filters, limit
            )
        if EmbedItemKind.BULLET in eligible:
            scored += await self._semantic_kind(
                user_id, EmbedItemKind.BULLET, Bulletpoint, distance, filters, limit
            )
        # Merge across kinds by ascending cosine distance (nearest first).
        scored.sort(key=lambda item: item[1])
        return [ref for ref, _distance in scored]

    async def graph_inputs(
        self,
        user_id: int,
        worklog_ids: set[int],
        bullet_ids: set[int],
        source_ids: set[int],
    ) -> GraphInputs:
        return await load_graph_inputs(self._session, user_id, worklog_ids, bullet_ids, source_ids)

    async def _lexical_worklog(
        self, user_id: int, tsquery: ColumnElement[object], filters: SearchFilters, limit: int
    ) -> list[tuple[ItemRef, float]]:
        rank = func.ts_rank_cd(WORKLOG_DOC, tsquery)
        statement = (
            select(WorklogEntry.id, rank.label("rank"))
            .where(
                WorklogEntry.user_id == user_id,
                WorklogEntry.archived_at.is_(None),
                WORKLOG_DOC.op("@@")(tsquery),
                *worklog_predicates(filters),
            )
            .order_by(rank.desc(), WorklogEntry.id)
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).all()
        return [(ItemRef(EmbedItemKind.WORKLOG, row.id), float(row.rank)) for row in rows]

    async def _lexical_source(
        self, user_id: int, tsquery: ColumnElement[object], filters: SearchFilters, limit: int
    ) -> list[tuple[ItemRef, float]]:
        # A source matches on its own label/summary or (for a role) company/title;
        # rank is the sum so a source strong on both ranks above one strong on one.
        rank = func.ts_rank_cd(SOURCE_DOC, tsquery) + func.coalesce(
            func.ts_rank_cd(ROLE_DOC, tsquery), 0.0
        )
        statement = (
            select(Source.id, rank.label("rank"))
            .select_from(Source)
            .outerjoin(Role, Role.source_id == Source.id)
            .where(
                Source.user_id == user_id,
                Source.archived_at.is_(None),
                or_(SOURCE_DOC.op("@@")(tsquery), ROLE_DOC.op("@@")(tsquery)),
                *source_predicates(filters),
            )
            .order_by(rank.desc(), Source.id)
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).all()
        return [(ItemRef(EmbedItemKind.SOURCE, row.id), float(row.rank)) for row in rows]

    async def _lexical_bullet(
        self, user_id: int, tsquery: ColumnElement[object], filters: SearchFilters, limit: int
    ) -> list[tuple[ItemRef, float]]:
        rank = func.ts_rank_cd(BULLET_DOC, tsquery)
        statement = (
            select(Bulletpoint.id, rank.label("rank"))
            .where(
                Bulletpoint.user_id == user_id,
                Bulletpoint.archived_at.is_(None),
                BULLET_DOC.op("@@")(tsquery),
                *bullet_predicates(filters),
            )
            .order_by(rank.desc(), Bulletpoint.id)
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).all()
        return [(ItemRef(EmbedItemKind.BULLET, row.id), float(row.rank)) for row in rows]

    async def _semantic_kind(
        self,
        user_id: int,
        kind: EmbedItemKind,
        model: type[WorklogEntry] | type[Source] | type[Bulletpoint],
        distance: ColumnElement[float],
        filters: SearchFilters,
        limit: int,
    ) -> list[tuple[ItemRef, float]]:
        predicates = {
            EmbedItemKind.WORKLOG: worklog_predicates,
            EmbedItemKind.SOURCE: source_predicates,
            EmbedItemKind.BULLET: bullet_predicates,
        }[kind](filters)
        statement = (
            select(model.id, distance.label("distance"))
            .select_from(Embedding)
            .join(model, model.id == Embedding.item_id)
            .where(
                Embedding.item_kind == kind,
                Embedding.user_id == user_id,
                model.archived_at.is_(None),
                *predicates,
            )
            .order_by(distance)
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).all()
        return [(ItemRef(kind, row.id), float(row.distance)) for row in rows]
