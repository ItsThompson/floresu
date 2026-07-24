"""Unit tests for the pure worklog label-normalization helper."""

from __future__ import annotations

from floresu.worklog.normalize import normalize_labels


def test_normalize_labels_trims_drops_blanks_and_dedupes_in_order() -> None:
    assert normalize_labels([" api ", "api", "  ", "python", "API"]) == ["api", "python", "API"]


def test_normalize_labels_of_an_empty_list_is_empty() -> None:
    assert normalize_labels([]) == []
