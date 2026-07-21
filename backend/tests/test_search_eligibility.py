"""Unit tests for the pure filter-eligibility policy.

A filter narrows the corpus; a filter that cannot apply to a kind excludes that
kind. These tests pin the per-filter kind sets and the way filters compose.
"""

from __future__ import annotations

from datetime import date

from floresu.embedding.config import EmbedItemKind
from floresu.profile.models import SourceKind
from floresu.search.eligibility import eligible_kinds
from floresu.search.schemas import DateRange, SearchFilters, SearchLayer

_ALL = {EmbedItemKind.WORKLOG, EmbedItemKind.BULLET, EmbedItemKind.SOURCE}


def test_default_both_layer_is_every_kind() -> None:
    assert eligible_kinds(SearchFilters()) == _ALL


def test_raw_layer_is_worklog_and_source() -> None:
    got = eligible_kinds(SearchFilters(layer=SearchLayer.RAW))
    assert got == {EmbedItemKind.WORKLOG, EmbedItemKind.SOURCE}


def test_library_layer_is_bullets_only() -> None:
    assert eligible_kinds(SearchFilters(layer=SearchLayer.LIBRARY)) == {EmbedItemKind.BULLET}


def test_kinds_filter_restricts_to_sources() -> None:
    got = eligible_kinds(SearchFilters(kinds=[SourceKind.ROLE]))
    assert got == {EmbedItemKind.SOURCE}


def test_tags_filter_restricts_to_worklog() -> None:
    assert eligible_kinds(SearchFilters(tags=["python"])) == {EmbedItemKind.WORKLOG}


def test_date_range_filter_excludes_bullets() -> None:
    got = eligible_kinds(SearchFilters(date_range=DateRange(to=date(2024, 1, 1))))
    assert got == {EmbedItemKind.WORKLOG, EmbedItemKind.SOURCE}


def test_kinds_and_tags_together_leave_nothing() -> None:
    # kinds keeps only sources, tags keeps only worklog: nothing is both.
    got = eligible_kinds(SearchFilters(kinds=[SourceKind.ROLE], tags=["python"]))
    assert got == set()


def test_kinds_and_date_range_intersect_to_sources() -> None:
    got = eligible_kinds(
        SearchFilters(kinds=[SourceKind.PROJECT], date_range=DateRange(to=date(2024, 1, 1)))
    )
    assert got == {EmbedItemKind.SOURCE}
