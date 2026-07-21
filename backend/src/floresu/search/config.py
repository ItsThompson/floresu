"""Search-domain constants and the pure limit-resolution helpers.

The RRF constant and the result-window bounds live here so the fusion module, the
retrieval repository, and the service read one source. The two limit helpers are
pure (an integer in, a clamped integer out), so they are unit-tested without any
I/O.
"""

from __future__ import annotations

# Reciprocal Rank Fusion constant: ``score = Σ 1 / (k + rank)``. Model-free and
# tunable; k = 60 is the value the spec pins (the widely used RRF default).
RRF_K = 60

# The result window. A query with no explicit limit returns the default; a caller
# may request up to the maximum. Bounded so an agent (or the Library view) cannot
# ask for an unbounded dump.
DEFAULT_SEARCH_LIMIT = 20
MAX_SEARCH_LIMIT = 100

# How many candidates each retriever fetches per kind before fusion. Fusion can
# only rank items it is given, so each retriever fetches a pool wider than the
# final window; the pool is bounded so a large requested limit cannot make a
# retriever scan without limit. At P0 per-user corpus sizes this fetches the whole
# matching set in practice.
_CANDIDATE_MULTIPLIER = 3
MAX_CANDIDATE_POOL = 200


def resolve_limit(requested: int | None) -> int:
    """Clamp a requested result limit into ``[1, MAX_SEARCH_LIMIT]``; default when unset."""
    if requested is None:
        return DEFAULT_SEARCH_LIMIT
    return max(1, min(requested, MAX_SEARCH_LIMIT))


def candidate_pool(limit: int) -> int:
    """The per-kind candidate count each retriever fetches for a resolved ``limit``."""
    return min(limit * _CANDIDATE_MULTIPLIER, MAX_CANDIDATE_POOL)
