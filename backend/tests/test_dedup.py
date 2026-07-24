"""Unit tests for the shared order-preserving de-duplication helper.

``dedupe`` is the single home for first-seen-unique collapsing across the write
seams (library bulletpoint writer, its copy-on-write path, and the worklog
writer). It must preserve first-seen order so a caller's edge set stays stable.
"""

from __future__ import annotations

from floresu.core.dedup import dedupe


def test_dedupe_preserves_first_seen_order() -> None:
    assert dedupe([3, 1, 3, 2, 1]) == [3, 1, 2]


def test_dedupe_of_an_empty_list_is_empty() -> None:
    assert dedupe([]) == []


def test_dedupe_leaves_an_already_unique_list_unchanged() -> None:
    assert dedupe([1, 2, 3]) == [1, 2, 3]


def test_dedupe_works_for_any_hashable_element_type() -> None:
    assert dedupe(["b", "a", "b", "c", "a"]) == ["b", "a", "c"]
