"""Corpus SQL fragments: the full-text documents and the per-kind filter predicates.

Two cohesive concerns the retrieval queries share, kept here so the repository
reads as query shape rather than fragment construction:

- the ``to_tsvector`` document expressions, written to match migration 0011's GIN
  expression indexes exactly (explicit ``::regconfig``, the same concatenation and
  ``COALESCE``) so the planner can use the indexes rather than scan;
- the per-kind filter predicates that translate a :class:`SearchFilters` into the
  ``WHERE`` clauses applicable to each corpus kind (a filter that does not apply to
  a kind is simply absent; :mod:`floresu.search.eligibility` decides which kinds
  run at all).

Both the lexical and semantic retrievers apply the same per-kind predicates, so an
archived-excluded, owner-scoped query narrows identically on either path.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import ColumnElement, literal_column, or_, select, text
from sqlalchemy.orm import InstrumentedAttribute

from floresu.library.models import Bulletpoint, BulletSource, BulletWorklog
from floresu.profile.models import Source
from floresu.worklog.models import Tag, WorklogEntry, WorklogSource, WorklogTag

if TYPE_CHECKING:
    from floresu.search.schemas import SearchFilters

# The ``regconfig`` literal and the four full-text documents, one per corpus text
# surface, matching migration 0011's GIN expression indexes.
REGCONFIG = text("'english'::regconfig")
WORKLOG_DOC: ColumnElement[Any] = literal_column(
    "to_tsvector('english'::regconfig, "
    "(worklog_entries.title || ' '::text) || COALESCE(worklog_entries.description, ''::text))"
)
SOURCE_DOC: ColumnElement[Any] = literal_column(
    "to_tsvector('english'::regconfig, "
    "(sources.display_label || ' '::text) || COALESCE(sources.summary, ''::text))"
)
ROLE_DOC: ColumnElement[Any] = literal_column(
    "to_tsvector('english'::regconfig, (roles.company || ' '::text) || roles.job_title)"
)
BULLET_DOC: ColumnElement[Any] = literal_column(
    "to_tsvector('english'::regconfig, bulletpoints.text)"
)


def worklog_predicates(filters: SearchFilters) -> list[ColumnElement[bool]]:
    """The ``WHERE`` predicates that narrow worklog hits: source attachment, tags, date."""
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


def source_predicates(filters: SearchFilters) -> list[ColumnElement[bool]]:
    """The ``WHERE`` predicates that narrow source hits: kind, id, active-period overlap."""
    predicates: list[ColumnElement[bool]] = []
    if filters.kinds is not None:
        predicates.append(Source.kind.in_(filters.kinds))
    if filters.source_ids is not None:
        predicates.append(Source.id.in_(filters.source_ids))
    if filters.date_range is not None:
        # A source's active period [date_start, date_end] must overlap the window;
        # NULL bounds (undated / ongoing) never exclude the source.
        if filters.date_range.from_ is not None:
            predicates.append(
                or_(Source.date_end.is_(None), Source.date_end >= filters.date_range.from_)
            )
        if filters.date_range.to is not None:
            predicates.append(
                or_(Source.date_start.is_(None), Source.date_start <= filters.date_range.to)
            )
    return predicates


def bullet_predicates(filters: SearchFilters) -> list[ColumnElement[bool]]:
    """The ``WHERE`` predicate that narrows bullet hits: attachment to a source in the set."""
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
