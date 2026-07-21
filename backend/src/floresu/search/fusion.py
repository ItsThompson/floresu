"""Reciprocal Rank Fusion: model-free, deterministic combination of ranked lists.

Two retrievers (lexical FTS and semantic pgvector ANN) each return a list of items
ordered best-first. RRF fuses them using only the rank of each item, no score
calibration and no reranker model:

    score(item) = Σ  1 / (k + rank_in_list)     over the lists it appears in

with ``rank_in_list`` 1-based and ``k = 60`` (:data:`floresu.search.config.RRF_K`).
Because an item present in both lists sums two contributions, it outranks an item
present in one list at the same rank. Ordering is deterministic: ties break by a
fixed kind order then item id, so identical inputs always yield an identical order.

This module is pure (ranked lists in, fused order out), so it is exhaustively
unit-tested with no retrieval or I/O.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from floresu.embedding.config import EmbedItemKind
from floresu.search.config import RRF_K

# A fixed kind order for deterministic tie-breaking (definition order of the enum:
# worklog, bullet, source).
_KIND_ORDER: dict[EmbedItemKind, int] = {kind: index for index, kind in enumerate(EmbedItemKind)}


@dataclass(frozen=True)
class ItemRef:
    """A corpus item identified by its kind and id; the fusion/graph hit key."""

    kind: EmbedItemKind
    item_id: int


@dataclass(frozen=True)
class FusedHit:
    """One fused result: the item and its combined RRF score."""

    ref: ItemRef
    score: float


def reciprocal_rank_fusion(
    ranked_lists: Iterable[Sequence[ItemRef]], *, k: int = RRF_K
) -> list[FusedHit]:
    """Fuse best-first ranked lists into one ranking by summed reciprocal ranks.

    Each list is independent and 1-based: an item's contribution from a list is
    ``1 / (k + position)``. The result is ordered by descending score, breaking
    ties by the fixed kind order then ascending item id, so the ordering is stable.
    """
    scores: dict[ItemRef, float] = {}
    for ranked in ranked_lists:
        for position, ref in enumerate(ranked, start=1):
            scores[ref] = scores.get(ref, 0.0) + 1.0 / (k + position)
    ordered = sorted(
        scores.items(),
        key=lambda item: (-item[1], _KIND_ORDER[item[0].kind], item[0].item_id),
    )
    return [FusedHit(ref=ref, score=score) for ref, score in ordered]
