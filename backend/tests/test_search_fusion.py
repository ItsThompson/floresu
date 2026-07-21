"""Unit tests for the pure Reciprocal Rank Fusion module.

RRF is model-free and rank-only: an item's score is the sum of ``1 / (k + rank)``
over the lists it appears in. These tests lock in the two properties the spec
requires: an item in both lists outranks one in a single list at the same rank,
and the ordering is deterministic (stable tie-breaking).
"""

from __future__ import annotations

from floresu.embedding.config import EmbedItemKind
from floresu.search.config import RRF_K
from floresu.search.fusion import FusedHit, ItemRef, reciprocal_rank_fusion

_W1 = ItemRef(EmbedItemKind.WORKLOG, 1)
_W2 = ItemRef(EmbedItemKind.WORKLOG, 2)
_B1 = ItemRef(EmbedItemKind.BULLET, 1)
_S1 = ItemRef(EmbedItemKind.SOURCE, 1)


def test_score_is_the_summed_reciprocal_rank() -> None:
    fused = reciprocal_rank_fusion([[_W1, _W2]])
    by_ref = {hit.ref: hit.score for hit in fused}
    assert by_ref[_W1] == 1.0 / (RRF_K + 1)
    assert by_ref[_W2] == 1.0 / (RRF_K + 2)


def test_an_item_in_both_lists_sums_and_outranks_a_single_list_item() -> None:
    # _W1 is rank 1 in both lists; _W2 is rank 1 in only the second. _W1 must rank
    # above _W2 even though both are "rank 1" in a list.
    fused = reciprocal_rank_fusion([[_W1], [_W1, _W2]])
    assert [hit.ref for hit in fused] == [_W1, _W2]
    scores = {hit.ref: hit.score for hit in fused}
    assert scores[_W1] == 2.0 / (RRF_K + 1)
    assert scores[_W2] == 1.0 / (RRF_K + 2)
    assert scores[_W1] > scores[_W2]


def test_ordering_is_deterministic_across_kinds_on_a_score_tie() -> None:
    # All three appear once at rank 1, so scores tie; the tie breaks by the fixed
    # kind order (worklog, bullet, source) then id, so the order is stable.
    fused = reciprocal_rank_fusion([[_S1], [_B1], [_W1]])
    assert [hit.ref for hit in fused] == [_W1, _B1, _S1]
    assert len({hit.score for hit in fused}) == 1


def test_a_tie_within_a_kind_breaks_by_ascending_id() -> None:
    fused = reciprocal_rank_fusion([[_W2], [_W1]])
    assert [hit.ref for hit in fused] == [_W1, _W2]


def test_empty_lists_fuse_to_nothing() -> None:
    assert reciprocal_rank_fusion([[], []]) == []


def test_the_tunable_k_changes_the_score_but_not_the_shape() -> None:
    fused = reciprocal_rank_fusion([[_W1]], k=1)
    assert fused == [FusedHit(ref=_W1, score=1.0 / (1 + 1))]
