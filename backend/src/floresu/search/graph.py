"""Pure assembly of the scored provenance DAG from a fused hit set.

The flat RRF ranking answers "what is most relevant"; this module rolls the SAME
hits into the provenance DAG so a consumer can walk any ``source → worklog →
bullet`` chain. It reuses :func:`floresu.library.provenance.build_provenance_dag`
(the shared, scoped three-join grouping), so "assemble the DAG" has
one definition.

Node rules:

- Worklog and bullet nodes are exactly the fused hits of that kind; each carries
  its fused score and its edges (a bullet spanning two parents is one node, never
  duplicated).
- Source nodes are the union of direct source hits and the sources that matched
  hits roll up to (via ``worklog_source`` / ``bullet_source``). A source carries a
  ``match_score`` only when it matched the query directly, and a ``score`` that
  combines that match score (if any) with the scores of its matched children, so a
  directly-matched source with no matching children still appears with its own
  score and is never lost.

It is pure: fused hits + node metadata + raw edges in, a :class:`SearchGraph` out.
Edge scoping to the hit set is delegated to ``build_provenance_dag``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from floresu.embedding.config import EmbedItemKind
from floresu.library.provenance import build_provenance_dag
from floresu.profile.models import SourceKind
from floresu.search.fusion import FusedHit, ItemRef
from floresu.search.schemas import (
    SearchBulletNode,
    SearchGraph,
    SearchSourceNode,
    SearchWorklogNode,
)


@dataclass(frozen=True)
class SourceMeta:
    """The display fields a source node carries, keyed by source id upstream."""

    kind: SourceKind
    label: str


@dataclass(frozen=True)
class WorklogMeta:
    """The display fields a worklog node carries, keyed by worklog id upstream."""

    title: str
    date: date


@dataclass(frozen=True)
class BulletMeta:
    """The display field a bullet node carries, keyed by bullet id upstream."""

    text: str


def assemble_graph(
    hits: Sequence[FusedHit],
    *,
    source_meta: Mapping[int, SourceMeta],
    worklog_meta: Mapping[int, WorklogMeta],
    bullet_meta: Mapping[int, BulletMeta],
    bullet_worklog_edges: Sequence[tuple[int, int]],
    bullet_source_edges: Sequence[tuple[int, int]],
    worklog_source_edges: Sequence[tuple[int, int]],
) -> SearchGraph:
    """Roll the fused hits into the scored provenance DAG (nodes + edges)."""
    scores = {hit.ref: hit.score for hit in hits}
    hit_worklog_ids = _ids_of(scores, EmbedItemKind.WORKLOG)
    hit_bullet_ids = _ids_of(scores, EmbedItemKind.BULLET)
    # Source nodes are the direct source hits plus every ancestor source metadata
    # was loaded for (the sources matched hits roll up to). ``source_meta`` already
    # excludes archived sources, so an archived ancestor never becomes a node.
    node_source_ids = set(source_meta)

    dag = build_provenance_dag(
        bullet_ids=hit_bullet_ids,
        worklog_ids=hit_worklog_ids,
        source_ids=node_source_ids,
        bullet_worklog_edges=bullet_worklog_edges,
        bullet_source_edges=bullet_source_edges,
        worklog_source_edges=worklog_source_edges,
    )

    worklog_nodes = _worklog_nodes(hit_worklog_ids, scores, worklog_meta, dag.worklog_source)
    bullet_nodes = _bullet_nodes(
        hit_bullet_ids, scores, bullet_meta, dag.bullet_worklog, dag.bullet_source
    )
    source_nodes = _source_nodes(
        source_meta,
        scores,
        worklog_scores={node.id: node.score for node in worklog_nodes},
        bullet_scores={node.id: node.score for node in bullet_nodes},
        worklog_source=dag.worklog_source,
        bullet_source=dag.bullet_source,
    )
    return SearchGraph(sources=source_nodes, worklog=worklog_nodes, bullets=bullet_nodes)


def _ids_of(scores: Mapping[ItemRef, float], kind: EmbedItemKind) -> set[int]:
    """The item ids of the fused hits of one kind."""
    return {ref.item_id for ref in scores if ref.kind is kind}


def _worklog_nodes(
    ids: set[int],
    scores: Mapping[ItemRef, float],
    meta: Mapping[int, WorklogMeta],
    worklog_source: Mapping[int, list[int]],
) -> list[SearchWorklogNode]:
    nodes = [
        SearchWorklogNode(
            id=worklog_id,
            title=meta[worklog_id].title,
            date=meta[worklog_id].date,
            score=scores[ItemRef(EmbedItemKind.WORKLOG, worklog_id)],
            source_ids=worklog_source.get(worklog_id, []),
        )
        for worklog_id in ids
        if worklog_id in meta
    ]
    return sorted(nodes, key=lambda node: (-node.score, node.id))


def _bullet_nodes(
    ids: set[int],
    scores: Mapping[ItemRef, float],
    meta: Mapping[int, BulletMeta],
    bullet_worklog: Mapping[int, list[int]],
    bullet_source: Mapping[int, list[int]],
) -> list[SearchBulletNode]:
    nodes = [
        SearchBulletNode(
            id=bullet_id,
            text=meta[bullet_id].text,
            score=scores[ItemRef(EmbedItemKind.BULLET, bullet_id)],
            worklog_ids=bullet_worklog.get(bullet_id, []),
            source_ids=bullet_source.get(bullet_id, []),
        )
        for bullet_id in ids
        if bullet_id in meta
    ]
    return sorted(nodes, key=lambda node: (-node.score, node.id))


def _source_nodes(
    meta: Mapping[int, SourceMeta],
    scores: Mapping[ItemRef, float],
    *,
    worklog_scores: Mapping[int, float],
    bullet_scores: Mapping[int, float],
    worklog_source: Mapping[int, list[int]],
    bullet_source: Mapping[int, list[int]],
) -> list[SearchSourceNode]:
    """Build each source node, combining its own match score with its children's.

    The node set is exactly the sources metadata was loaded for (direct hits plus
    the non-archived ancestors matched hits roll up to). A source's children are
    the matched worklog entries that roll up to it (``worklog_source``) and the
    matched bullets that frame it (``bullet_source``); its ``score`` is its match
    score (if it matched directly) plus every matched child's score.
    """
    child_worklogs = _invert(worklog_source)
    child_bullets = _invert(bullet_source)
    nodes: list[SearchSourceNode] = []
    for source_id, source in meta.items():
        match_score = scores.get(ItemRef(EmbedItemKind.SOURCE, source_id))
        children_total = sum(
            worklog_scores[worklog_id] for worklog_id in child_worklogs.get(source_id, ())
        ) + sum(bullet_scores[bullet_id] for bullet_id in child_bullets.get(source_id, ()))
        nodes.append(
            SearchSourceNode(
                id=source_id,
                kind=source.kind,
                label=source.label,
                match_score=match_score,
                score=(match_score or 0.0) + children_total,
            )
        )
    return sorted(nodes, key=lambda node: (-node.score, node.id))


def _invert(parent_to_children: Mapping[int, list[int]]) -> dict[int, list[int]]:
    """Invert a child→parents adjacency (e.g. worklog→sources) to parent→children."""
    inverted: dict[int, list[int]] = {}
    for child, parents in parent_to_children.items():
        for parent in parents:
            inverted.setdefault(parent, []).append(child)
    return inverted
