"""The pure provenance-DAG assembly: the three joins grouped and scoped, no I/O.

A bullet's provenance is a DAG over three many-to-many joins: ``bullet_worklog``
(a bullet frames a worklog entry), ``bullet_source`` (a bullet frames a source
directly), and ``worklog_source`` (a worklog entry rolls up to a source). This
module takes the raw edge rows plus the node-id sets that scope them and returns
the DAG grouped by parent, with each node appearing once and its children unique
and sorted.

It is pure (edges in, adjacency out; no session, no query), so the library reads
and the hybrid-search module (which loads the edges for its hit set) share one
definition of "assemble the provenance DAG" and both can unit-test it in
isolation. Scoping to the provided id sets is intrinsic: an edge is kept only when
both of its endpoints are in the sets, so a caller passes the hit set it cares
about and gets exactly the sub-DAG spanning it.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class ProvenanceDag:
    """The three provenance joins grouped by parent; each node appears once.

    Every mapping keys a parent id to the sorted, de-duplicated child ids it
    connects to, so a bullet framing two worklog entries is one key with two
    children (never duplicated) and a worklog rolling up to two sources is one key
    with two children.
    """

    # bullet id -> the worklog ids that bullet frames
    bullet_worklog: dict[int, list[int]]
    # bullet id -> the source ids that bullet frames directly
    bullet_source: dict[int, list[int]]
    # worklog id -> the source ids that worklog entry rolls up to
    worklog_source: dict[int, list[int]]


def build_provenance_dag(
    *,
    bullet_ids: Collection[int],
    worklog_ids: Collection[int],
    source_ids: Collection[int],
    bullet_worklog_edges: Iterable[tuple[int, int]],
    bullet_source_edges: Iterable[tuple[int, int]],
    worklog_source_edges: Iterable[tuple[int, int]],
) -> ProvenanceDag:
    """Group the three joins by parent, scoped to the given node-id sets.

    Each ``*_edges`` iterable is ``(parent_id, child_id)`` rows for one join. An
    edge is kept only when both endpoints are in the corresponding id sets, so the
    result is exactly the sub-DAG spanning the provided nodes.
    """
    bullets = set(bullet_ids)
    worklogs = set(worklog_ids)
    sources = set(source_ids)
    return ProvenanceDag(
        bullet_worklog=_group(bullet_worklog_edges, parents=bullets, children=worklogs),
        bullet_source=_group(bullet_source_edges, parents=bullets, children=sources),
        worklog_source=_group(worklog_source_edges, parents=worklogs, children=sources),
    )


def _group(
    edges: Iterable[tuple[int, int]], *, parents: set[int], children: set[int]
) -> dict[int, list[int]]:
    """Group child ids under each parent, keeping only edges within both id sets."""
    grouped: dict[int, set[int]] = {}
    for parent, child in edges:
        if parent in parents and child in children:
            grouped.setdefault(parent, set()).add(child)
    return {parent: sorted(children) for parent, children in grouped.items()}
