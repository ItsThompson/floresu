"""Unit tests for the pure worklog input-normalization helpers."""

from __future__ import annotations

from floresu.worklog.normalize import dedupe, normalize_labels


def test_normalize_labels_trims_drops_blanks_and_dedupes_in_order() -> None:
    assert normalize_labels([" api ", "api", "  ", "python", "API"]) == ["api", "python", "API"]


def test_normalize_labels_of_an_empty_list_is_empty() -> None:
    assert normalize_labels([]) == []


def test_dedupe_preserves_first_seen_order() -> None:
    assert dedupe([3, 1, 3, 2, 1]) == [3, 1, 2]


def test_dedupe_of_an_empty_list_is_empty() -> None:
    assert dedupe([]) == []
