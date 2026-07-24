"""Pure label-normalization helper for worklog write input.

A worklog write's tag labels are normalized before the service reconciles them,
so the same rules apply on create and edit: labels are trimmed, blank labels
dropped, and duplicates removed with first-seen order kept. A pure function, kept
out of the service so it is unit-testable in isolation. Source-id de-duplication
uses the shared ``floresu.core.dedup`` helper.
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
