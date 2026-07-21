"""Pure filter policy: which corpus kinds a set of filters leaves eligible.

A filter narrows the corpus. ``layer`` selects whole kinds; the other filters are
attributes of a specific kind, so a filter that cannot apply to a kind excludes
that kind entirely (that is what "narrow as specified" means: a ``tags`` filter
returns tagged worklog entries, not every source and bullet as well):

- ``kinds`` is the source-kind discriminator, so it restricts to sources.
- ``tags`` are worklog tag labels, so they restrict to worklog entries.
- ``date_range`` is an intrinsic date, which only worklog entries and sources
  have (a canonical bullet has none of its own), so it excludes bullets.
- ``source_ids`` is a provenance attachment every kind can satisfy, so it narrows
  within each kind rather than excluding a kind.

This is pure (filters in, a kind set out), so it is exhaustively unit-tested and
the retrieval repository just runs a query per eligible kind, applying that kind's
applicable predicates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.embedding.config import EmbedItemKind
from floresu.search.schemas import SearchLayer

if TYPE_CHECKING:
    from floresu.search.schemas import SearchFilters

_RAW_KINDS = frozenset({EmbedItemKind.WORKLOG, EmbedItemKind.SOURCE})
_LIBRARY_KINDS = frozenset({EmbedItemKind.BULLET})

_LAYER_KINDS: dict[SearchLayer, frozenset[EmbedItemKind]] = {
    SearchLayer.RAW: _RAW_KINDS,
    SearchLayer.LIBRARY: _LIBRARY_KINDS,
    SearchLayer.BOTH: _RAW_KINDS | _LIBRARY_KINDS,
}


def eligible_kinds(filters: SearchFilters) -> frozenset[EmbedItemKind]:
    """The corpus kinds still searchable after applying every provided filter."""
    eligible = _LAYER_KINDS[filters.layer]
    if filters.kinds is not None:
        eligible &= {EmbedItemKind.SOURCE}
    if filters.tags is not None:
        eligible &= {EmbedItemKind.WORKLOG}
    if filters.date_range is not None:
        eligible &= {EmbedItemKind.WORKLOG, EmbedItemKind.SOURCE}
    return eligible
