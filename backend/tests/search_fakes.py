"""In-memory test doubles for the search module.

The service is tested sociably: the real :class:`SearchService`, real RRF fusion,
and real graph assembly run over an in-memory :class:`SearchRepository` that stands
in only at the true external boundary (Postgres). The repo returns seeded lexical
and semantic hit orders and assembles graph inputs from a seeded corpus the same
way the SQL repository does (edges scoped to the hit set, ancestor sources rolled
in, archived sources excluded), so the graph the service returns is exercised end
to end without a database. The query embedding uses a fake provider (no OpenAI);
:class:`FailingEmbeddingProvider` drives the lexical-only degradation path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from floresu.embedding.config import EMBEDDING_DIMENSION, EMBEDDING_MODEL, EmbedItemKind
from floresu.profile.models import SourceKind
from floresu.search.fusion import ItemRef
from floresu.search.graph import BulletMeta, SourceMeta, WorklogMeta
from floresu.search.retrieval import GraphInputs
from floresu.search.schemas import SearchFilters


@dataclass
class _Corpus:
    """A tiny seeded corpus the fake repository resolves graph inputs from."""

    worklog: dict[int, WorklogMeta] = field(default_factory=dict)
    bullet: dict[int, BulletMeta] = field(default_factory=dict)
    source: dict[int, SourceMeta] = field(default_factory=dict)
    bullet_worklog: list[tuple[int, int]] = field(default_factory=list)
    bullet_source: list[tuple[int, int]] = field(default_factory=list)
    worklog_source: list[tuple[int, int]] = field(default_factory=list)


class InMemorySearchRepository:
    """A dict-backed :class:`SearchRepository` with seeded retrieval and corpus."""

    def __init__(self) -> None:
        self.lexical_hits: list[ItemRef] = []
        self.semantic_hits: list[ItemRef] = []
        self.corpus = _Corpus()
        self.semantic_vectors: list[list[float]] = []

    def add_worklog(self, worklog_id: int, title: str, when: date) -> None:
        self.corpus.worklog[worklog_id] = WorklogMeta(title=title, date=when)

    def add_bullet(self, bullet_id: int, text: str) -> None:
        self.corpus.bullet[bullet_id] = BulletMeta(text=text)

    def add_source(self, source_id: int, kind: SourceKind, label: str) -> None:
        self.corpus.source[source_id] = SourceMeta(kind=kind, label=label)

    async def lexical(
        self,
        user_id: int,
        query: str,
        filters: SearchFilters,
        eligible: frozenset[EmbedItemKind],
        limit: int,
    ) -> list[ItemRef]:
        return [ref for ref in self.lexical_hits if ref.kind in eligible][:limit]

    async def semantic(
        self,
        user_id: int,
        query_vector: list[float],
        filters: SearchFilters,
        eligible: frozenset[EmbedItemKind],
        limit: int,
    ) -> list[ItemRef]:
        self.semantic_vectors.append(query_vector)
        return [ref for ref in self.semantic_hits if ref.kind in eligible][:limit]

    async def graph_inputs(
        self,
        user_id: int,
        worklog_ids: set[int],
        bullet_ids: set[int],
        source_ids: set[int],
    ) -> GraphInputs:
        bullet_worklog = [edge for edge in self.corpus.bullet_worklog if edge[0] in bullet_ids]
        bullet_source = [edge for edge in self.corpus.bullet_source if edge[0] in bullet_ids]
        worklog_source = [edge for edge in self.corpus.worklog_source if edge[0] in worklog_ids]
        ancestors = (
            source_ids
            | {source_id for _b, source_id in bullet_source}
            | {source_id for _w, source_id in worklog_source}
        )
        return GraphInputs(
            source_meta={
                source_id: meta
                for source_id, meta in self.corpus.source.items()
                if source_id in ancestors
            },
            worklog_meta={
                worklog_id: meta
                for worklog_id, meta in self.corpus.worklog.items()
                if worklog_id in worklog_ids
            },
            bullet_meta={
                bullet_id: meta
                for bullet_id, meta in self.corpus.bullet.items()
                if bullet_id in bullet_ids
            },
            bullet_worklog_edges=bullet_worklog,
            bullet_source_edges=bullet_source,
            worklog_source_edges=worklog_source,
        )


class FailingEmbeddingProvider:
    """A provider whose ``embed`` always raises, to drive the degradation path."""

    model = EMBEDDING_MODEL
    dimension = EMBEDDING_DIMENSION

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("provider unavailable")
