"""Retrieval over the corpus: lexical FTS and semantic pgvector ANN, plus the
graph inputs for a hit set.

The service depends on the :class:`SearchRepository` interface and receives a
concrete binding, so tests substitute an in-memory double at the one true external
boundary (Postgres) while production binds :class:`SqlAlchemySearchRepository`.

Two retrievers run per eligible kind and each returns a best-first list of
:class:`~floresu.search.fusion.ItemRef`:

- **lexical** matches ``to_tsvector`` documents against ``websearch_to_tsquery`` and
  ranks by ``ts_rank_cd`` (the same GIN-indexed expressions migration 0011 built);
- **semantic** orders the item's stored vector by cosine distance to the query
  vector (the HNSW-indexed ``embeddings`` table).

Every retrieval is scoped to the owner and ``archived_at IS NULL`` and applies the
filter predicates applicable to each kind, so an archived item and a filtered-out
item never enter the ranking. :meth:`graph_inputs` loads the node metadata and the
three provenance joins for a hit set (scoped to the owner), which the pure graph
assembly rolls into the DAG.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any, Protocol

from sqlalchemy import ColumnElement, func, literal_column, or_, select, text
from sqlalchemy.orm import InstrumentedAttribute

from floresu.embedding.config import EmbedItemKind
from floresu.embedding.models import Embedding
from floresu.library.models import Bulletpoint, BulletSource, BulletWorklog
from floresu.profile.models import Role, Source
from floresu.search.fusion import ItemRef
from floresu.search.graph import BulletMeta, SourceMeta, WorklogMeta
from floresu.worklog.models import Tag, WorklogEntry, WorklogSource, WorklogTag

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.search.schemas import SearchFilters

# The full-text ``to_tsvector`` documents, written to match migration 0011's GIN
# expression indexes exactly (explicit ``::regconfig``, the same concatenation and
# ``COALESCE``), so the planner can use the indexes rather than scan.
_REGCONFIG = text("'english'::regconfig")
_WORKLOG_DOC: ColumnElement[Any] = literal_column(
    "to_tsvector('english'::regconfig, "
    "(worklog_entries.title || ' '::text) || COALESCE(worklog_entries.description, ''::text))"
)
_SOURCE_DOC: ColumnElement[Any] = literal_column(
    "to_tsvector('english'::regconfig, "
    "(sources.display_label || ' '::text) || COALESCE(sources.summary, ''::text))"
)
_ROLE_DOC: ColumnElement[Any] = literal_column(
    "to_tsvector('english'::regconfig, (roles.company || ' '::text) || roles.job_title)"
)
_BULLET_DOC: ColumnElement[Any] = literal_column(
    "to_tsvector('english'::regconfig, bulletpoints.text)"
)


@dataclass(frozen=True)
class GraphInputs:
    """Node metadata and the three provenance joins for a hit set (owner-scoped)."""

    source_meta: dict[int, SourceMeta]
    worklog_meta: dict[int, WorklogMeta]
    bullet_meta: dict[int, BulletMeta]
    bullet_worklog_edges: list[tuple[int, int]]
    bullet_source_edges: list[tuple[int, int]]
    worklog_source_edges: list[tuple[int, int]]


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
        tsquery = func.websearch_to_tsquery(_REGCONFIG, query)
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

    async def _lexical_worklog(
        self, user_id: int, tsquery: ColumnElement[object], filters: SearchFilters, limit: int
    ) -> list[tuple[ItemRef, float]]:
        rank = func.ts_rank_cd(_WORKLOG_DOC, tsquery)
        statement = (
            select(WorklogEntry.id, rank.label("rank"))
            .where(
                WorklogEntry.user_id == user_id,
                WorklogEntry.archived_at.is_(None),
                _WORKLOG_DOC.op("@@")(tsquery),
                *self._worklog_predicates(filters),
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
        rank = func.ts_rank_cd(_SOURCE_DOC, tsquery) + func.coalesce(
            func.ts_rank_cd(_ROLE_DOC, tsquery), 0.0
        )
        statement = (
            select(Source.id, rank.label("rank"))
            .select_from(Source)
            .outerjoin(Role, Role.source_id == Source.id)
            .where(
                Source.user_id == user_id,
                Source.archived_at.is_(None),
                or_(_SOURCE_DOC.op("@@")(tsquery), _ROLE_DOC.op("@@")(tsquery)),
                *self._source_predicates(filters),
            )
            .order_by(rank.desc(), Source.id)
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).all()
        return [(ItemRef(EmbedItemKind.SOURCE, row.id), float(row.rank)) for row in rows]

    async def _lexical_bullet(
        self, user_id: int, tsquery: ColumnElement[object], filters: SearchFilters, limit: int
    ) -> list[tuple[ItemRef, float]]:
        rank = func.ts_rank_cd(_BULLET_DOC, tsquery)
        statement = (
            select(Bulletpoint.id, rank.label("rank"))
            .where(
                Bulletpoint.user_id == user_id,
                Bulletpoint.archived_at.is_(None),
                _BULLET_DOC.op("@@")(tsquery),
                *self._bullet_predicates(filters),
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
            EmbedItemKind.WORKLOG: self._worklog_predicates,
            EmbedItemKind.SOURCE: self._source_predicates,
            EmbedItemKind.BULLET: self._bullet_predicates,
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

    def _worklog_predicates(self, filters: SearchFilters) -> list[ColumnElement[bool]]:
        predicates: list[ColumnElement[bool]] = []
        if filters.source_ids is not None:
            predicates.append(
                select(WorklogSource.worklog_id)
                .where(
                    WorklogSource.worklog_id == WorklogEntry.id,
                    WorklogSource.source_id.in_(filters.source_ids),
                )
                .exists()
            )
        if filters.tags is not None:
            predicates.append(
                select(WorklogTag.worklog_id)
                .join(Tag, Tag.id == WorklogTag.tag_id)
                .where(WorklogTag.worklog_id == WorklogEntry.id, Tag.label.in_(filters.tags))
                .exists()
            )
        predicates += _date_range_predicates(WorklogEntry.entry_date, filters)
        return predicates

    def _source_predicates(self, filters: SearchFilters) -> list[ColumnElement[bool]]:
        predicates: list[ColumnElement[bool]] = []
        if filters.kinds is not None:
            predicates.append(Source.kind.in_(filters.kinds))
        if filters.source_ids is not None:
            predicates.append(Source.id.in_(filters.source_ids))
        if filters.date_range is not None:
            # A source's active period [date_start, date_end] must overlap the
            # window; NULL bounds (undated / ongoing) never exclude the source.
            if filters.date_range.from_ is not None:
                predicates.append(
                    or_(Source.date_end.is_(None), Source.date_end >= filters.date_range.from_)
                )
            if filters.date_range.to is not None:
                predicates.append(
                    or_(Source.date_start.is_(None), Source.date_start <= filters.date_range.to)
                )
        return predicates

    def _bullet_predicates(self, filters: SearchFilters) -> list[ColumnElement[bool]]:
        predicates: list[ColumnElement[bool]] = []
        if filters.source_ids is not None:
            # Attached to a source in the set directly (bullet_source) or through a
            # framed worklog entry that rolls up to it (bullet_worklog ∘ worklog_source).
            direct = (
                select(BulletSource.bullet_id)
                .where(
                    BulletSource.bullet_id == Bulletpoint.id,
                    BulletSource.source_id.in_(filters.source_ids),
                )
                .exists()
            )
            via_worklog = (
                select(BulletWorklog.bullet_id)
                .join(WorklogSource, WorklogSource.worklog_id == BulletWorklog.worklog_id)
                .where(
                    BulletWorklog.bullet_id == Bulletpoint.id,
                    WorklogSource.source_id.in_(filters.source_ids),
                )
                .exists()
            )
            predicates.append(or_(direct, via_worklog))
        return predicates

    async def graph_inputs(
        self,
        user_id: int,
        worklog_ids: set[int],
        bullet_ids: set[int],
        source_ids: set[int],
    ) -> GraphInputs:
        worklog_meta = await self._worklog_meta(user_id, worklog_ids)
        bullet_meta = await self._bullet_meta(user_id, bullet_ids)
        bullet_worklog_edges = await self._edges(
            BulletWorklog.bullet_id, BulletWorklog.worklog_id, BulletWorklog.bullet_id, bullet_ids
        )
        bullet_source_edges = await self._edges(
            BulletSource.bullet_id, BulletSource.source_id, BulletSource.bullet_id, bullet_ids
        )
        worklog_source_edges = await self._edges(
            WorklogSource.worklog_id,
            WorklogSource.source_id,
            WorklogSource.worklog_id,
            worklog_ids,
        )
        # Node sources are the direct source hits plus the ancestors matched hits
        # roll up to; archived ancestors are dropped by the owner-scoped metadata read.
        ancestor_source_ids = (
            source_ids
            | {source_id for _b, source_id in bullet_source_edges}
            | {source_id for _w, source_id in worklog_source_edges}
        )
        source_meta = await self._source_meta(user_id, ancestor_source_ids)
        return GraphInputs(
            source_meta=source_meta,
            worklog_meta=worklog_meta,
            bullet_meta=bullet_meta,
            bullet_worklog_edges=bullet_worklog_edges,
            bullet_source_edges=bullet_source_edges,
            worklog_source_edges=worklog_source_edges,
        )

    async def _worklog_meta(self, user_id: int, ids: set[int]) -> dict[int, WorklogMeta]:
        if not ids:
            return {}
        rows = (
            await self._session.execute(
                select(WorklogEntry.id, WorklogEntry.title, WorklogEntry.entry_date).where(
                    WorklogEntry.user_id == user_id, WorklogEntry.id.in_(ids)
                )
            )
        ).all()
        return {row.id: WorklogMeta(title=row.title, date=row.entry_date) for row in rows}

    async def _bullet_meta(self, user_id: int, ids: set[int]) -> dict[int, BulletMeta]:
        if not ids:
            return {}
        rows = (
            await self._session.execute(
                select(Bulletpoint.id, Bulletpoint.text).where(
                    Bulletpoint.user_id == user_id, Bulletpoint.id.in_(ids)
                )
            )
        ).all()
        return {row.id: BulletMeta(text=row.text) for row in rows}

    async def _source_meta(self, user_id: int, ids: set[int]) -> dict[int, SourceMeta]:
        if not ids:
            return {}
        rows = (
            await self._session.execute(
                select(Source.id, Source.kind, Source.display_label).where(
                    Source.user_id == user_id,
                    Source.id.in_(ids),
                    Source.archived_at.is_(None),
                )
            )
        ).all()
        return {row.id: SourceMeta(kind=row.kind, label=row.display_label) for row in rows}

    async def _edges(
        self,
        parent_col: InstrumentedAttribute[int],
        child_col: InstrumentedAttribute[int],
        scope_col: InstrumentedAttribute[int],
        parent_ids: set[int],
    ) -> list[tuple[int, int]]:
        """Load ``(parent, child)`` edge rows for a set of parent ids, or none if empty."""
        if not parent_ids:
            return []
        rows = (
            await self._session.execute(
                select(parent_col, child_col).where(scope_col.in_(parent_ids))
            )
        ).all()
        return [(row[0], row[1]) for row in rows]


def _date_range_predicates(
    column: InstrumentedAttribute[date], filters: SearchFilters
) -> list[ColumnElement[bool]]:
    """Inclusive lower/upper bounds on a single date column (worklog entry date)."""
    if filters.date_range is None:
        return []
    predicates: list[ColumnElement[bool]] = []
    if filters.date_range.from_ is not None:
        predicates.append(column >= filters.date_range.from_)
    if filters.date_range.to is not None:
        predicates.append(column <= filters.date_range.to)
    return predicates
