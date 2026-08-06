"""Lean search wire schemas (re-declared, not imported).

``search_experience`` is the one search tool. Its input is a free-text ``query``
plus a :class:`SearchFilters`; its output is a :class:`SearchResult`
carrying the flat RRF-ranked list and the same hits rolled into the scored
provenance DAG (:class:`SearchGraph`: sources / worklog / bullets with edges and
scores), so the agent reconstructs the hierarchy in one call.

Field names are snake_case to match the backend wire surface; the one aliased
field is ``date_range``'s ``from`` (a Python keyword). Filter input forbids
unknown fields; result outputs ignore them so a backend addition never breaks a
read. The contract tests in ``contract/tests/`` keep every mirror honest.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from floresu_mcp.schemas_profile import SourceKind


class SearchLayer(StrEnum):
    """Which layers of the corpus a query searches; ``both`` by default."""

    RAW = "raw"  # worklog entries + profile sources
    LIBRARY = "library"  # canonical bulletpoints
    BOTH = "both"


class RankedItemKind(StrEnum):
    """The kind of a flat ranked hit (the three embeddable corpus kinds)."""

    WORKLOG = "worklog"
    BULLET = "bullet"
    SOURCE = "source"


class DateRange(BaseModel):
    """An inclusive date window; either bound may be omitted for an open range."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # ``from`` is a Python keyword, so the field is ``from_`` aliased to the wire
    # name ``from`` (accepted on input via populate_by_name, sent by alias).
    from_: date | None = Field(default=None, alias="from")
    to: date | None = None


class SearchFilters(BaseModel):
    """Optional filters that narrow the corpus before retrieval and fusion.

    Each provided filter narrows the eligible corpus. Filtering by ``kinds``
    restricts results to matching **source** nodes (a kind that cannot apply to
    worklog/bullet excludes them), so ``kinds=["role"]`` returns the matching role
    sources, not the accomplishments under them; to reach those, search the role's
    text or narrow by ``source_ids``.
    """

    model_config = ConfigDict(extra="forbid")

    source_ids: list[int] | None = None
    kinds: list[SourceKind] | None = None
    tags: list[str] | None = None
    layer: SearchLayer = SearchLayer.BOTH
    date_range: DateRange | None = None
    limit: int | None = Field(default=None, ge=1)


class RankedHit(BaseModel):
    """One entry in the flat RRF-ranked list: what matched and its fused score."""

    model_config = ConfigDict(extra="ignore")

    type: RankedItemKind
    id: int
    score: float


class SearchSourceNode(BaseModel):
    """A source in the graph: a direct hit and/or the parent of matched children.

    ``match_score`` is present only when the source matched the query directly;
    ``score`` combines that match (if any) with its matched children's scores.
    """

    model_config = ConfigDict(extra="ignore")

    id: int
    kind: SourceKind
    label: str
    match_score: float | None = None
    score: float


class SearchWorklogNode(BaseModel):
    """A matched worklog entry and its edges up to sources."""

    model_config = ConfigDict(extra="ignore")

    id: int
    title: str
    date: date
    score: float
    source_ids: list[int]


class SearchBulletNode(BaseModel):
    """A matched canonical bullet and its edges to worklog entries and sources."""

    model_config = ConfigDict(extra="ignore")

    id: int
    text: str
    score: float
    worklog_ids: list[int]
    source_ids: list[int]


class SearchGraph(BaseModel):
    """The hit set rolled into the provenance DAG: nodes carrying scores + edges."""

    model_config = ConfigDict(extra="ignore")

    sources: list[SearchSourceNode]
    worklog: list[SearchWorklogNode]
    bullets: list[SearchBulletNode]


class SearchNotice(BaseModel):
    """A soft, non-fatal notice (e.g. semantic retrieval degraded to lexical-only)."""

    model_config = ConfigDict(extra="ignore")

    code: str
    message: str


class SearchResult(BaseModel):
    """The search response: the flat ranked list, the scored DAG, and any notices."""

    model_config = ConfigDict(extra="ignore")

    ranked: list[RankedHit]
    graph: SearchGraph
    notices: list[SearchNotice] = Field(default_factory=list)
