"""Order-preserving de-duplication shared across the write seams.

Several write paths collapse an inbound id list to its first-seen-unique form
before persisting the edge set: the library bulletpoint writer, its
copy-on-write path, and the worklog writer. This module is the single home for
that operation so each caller imports it rather than redefining a
``dict.fromkeys`` (or a hand-rolled seen-set) copy under a per-domain name.
"""

from __future__ import annotations

from collections.abc import Hashable, Sequence


def dedupe[T: Hashable](items: Sequence[T]) -> list[T]:
    """Return ``items`` with duplicates removed, preserving first-seen order."""
    return list(dict.fromkeys(items))
