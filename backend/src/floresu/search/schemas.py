"""Wire schemas for the search module: the query in, the scored DAG out.

The request is a :class:`SearchQuery` (a query string plus optional filters); the
response is a :class:`SearchResult` carrying a flat RRF-ranked list and the same
hits rolled into the provenance DAG (nodes + edges). Field names are snake_case to
match the rest of the backend wire surface (the codebase, e.g.
``BulletpointRecord``, uses snake_case, and the MCP tool + generated frontend
client mirror the backend types). The one nested object that keeps the wire names
``from`` / ``to`` is ``date_range``, because ``from`` is a Python keyword the field
aliases around.

Filter semantics (each provided filter narrows the eligible corpus; see
:mod:`floresu.search.eligibility` for how a filter that cannot apply to a kind
excludes that kind):

- ``layer``: ``raw`` = worklog + sources, ``library`` = canonical bullets,
  ``both`` = all (default).
- ``kinds``: the source-kind discriminator; restricts results to matching sources.
- ``tags``: worklog tag labels; restricts results to matching worklog entries.
- ``source_ids``: restricts to items attached to those sources.
- ``date_range``: restricts dated items (worklog entry date, source active period).
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from floresu.embedding.config import EmbedItemKind
from floresu.profile.models import SourceKind
from floresu.search.config import MAX_SEARCH_LIMIT


class SearchLayer(StrEnum):
    """Which layers of the corpus a query searches; ``both`` by default."""

    RAW = "raw"  # worklog entries + profile sources (ground truth)
    LIBRARY = "library"  # canonical bulletpoints
    BOTH = "both"


class DateRange(BaseModel):
    """An inclusive date window; either bound may be omitted for an open range."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # ``from`` is a Python keyword, so the field is ``from_`` aliased to the wire
    # name ``from`` (accepted on input via populate_by_name).
    from_: date | None = Field(default=None, alias="from")
    to: date | None = None


class SearchFilters(BaseModel):
    """Optional filters that narrow the corpus before retrieval and fusion."""

    model_config = ConfigDict(extra="forbid")

    source_ids: list[int] | None = None
    kinds: list[SourceKind] | None = None
    tags: list[str] | None = None
    layer: SearchLayer = SearchLayer.BOTH
    date_range: DateRange | None = None
    limit: int | None = Field(default=None, ge=1, le=MAX_SEARCH_LIMIT)


class SearchQuery(BaseModel):
    """The one search input: a free-text query plus optional filters."""

    model_config = ConfigDict(extra="forbid")

    query: str
    filters: SearchFilters = Field(default_factory=SearchFilters)


class RankedHit(BaseModel):
    """One entry in the flat RRF-ranked list: what matched and its fused score."""

    type: EmbedItemKind
    id: int
    score: float


class SearchSourceNode(BaseModel):
    """A source in the graph: a direct hit and/or the parent of matched children.

    ``match_score`` is this source's own retrieval score, present only when the
    source matched the query directly. ``score`` is its ranking score: the match
    score (if any) combined with the scores of its matched children.
    """

    id: int
    kind: SourceKind
    label: str
    match_score: float | None = None
    score: float


class SearchWorklogNode(BaseModel):
    """A matched worklog entry and its edges up to sources."""

    id: int
    title: str
    date: date
    score: float
    source_ids: list[int]


class SearchBulletNode(BaseModel):
    """A matched canonical bullet and its edges to worklog entries and sources."""

    id: int
    text: str
    score: float
    worklog_ids: list[int]
    source_ids: list[int]


class SearchGraph(BaseModel):
    """The hit set rolled into the provenance DAG: nodes carrying scores + edges."""

    sources: list[SearchSourceNode]
    worklog: list[SearchWorklogNode]
    bullets: list[SearchBulletNode]


class SearchNotice(BaseModel):
    """A soft, non-fatal notice (e.g. semantic retrieval degraded to lexical-only)."""

    code: str
    message: str


class SearchResult(BaseModel):
    """The search response: the flat ranked list, the scored DAG, and any notices."""

    ranked: list[RankedHit]
    graph: SearchGraph
    notices: list[SearchNotice] = Field(default_factory=list)


# The soft-degradation notice raised when the query embedding could not be
# produced, so the query ran lexical-only. Machine-recoverable: the agent (or the
# UI) can surface it and optionally retry rather than treat the query as failed.
SEMANTIC_UNAVAILABLE = SearchNotice(
    code="semantic_unavailable",
    message="Semantic search was unavailable; results are lexical-only.",
)


def empty_result(notices: list[SearchNotice] | None = None) -> SearchResult:
    """A well-formed empty result (empty query, or a filter that matches nothing)."""
    return SearchResult(
        ranked=[],
        graph=SearchGraph(sources=[], worklog=[], bullets=[]),
        notices=notices or [],
    )
