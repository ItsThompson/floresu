"""Pure normalization helpers for worklog write input.

A worklog write's tag labels and source-id list are normalized before the service
reconciles them, so the same rules apply on create and edit: labels are trimmed,
blank labels dropped, and both lists de-duplicated with first-seen order kept.
Pure functions, kept out of the service so they are unit-testable in isolation.
"""

from __future__ import annotations

from collections.abc import Sequence


def normalize_labels(labels: Sequence[str]) -> list[str]:
    """Trim, drop blanks, and de-duplicate labels, preserving first-seen order."""
    seen: set[str] = set()
    normalized: list[str] = []
    for label in labels:
        trimmed = label.strip()
        if trimmed and trimmed not in seen:
            seen.add(trimmed)
            normalized.append(trimmed)
    return normalized


def dedupe(source_ids: Sequence[int]) -> list[int]:
    """De-duplicate source ids, preserving first-seen order."""
    seen: set[int] = set()
    unique: list[int] = []
    for source_id in source_ids:
        if source_id not in seen:
            seen.add(source_id)
            unique.append(source_id)
    return unique
