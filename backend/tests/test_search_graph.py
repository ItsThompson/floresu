"""Unit tests for the pure scored-provenance-DAG assembly.

Rolls a fused hit set into nodes + edges. Asserts: each node appears once (a
bullet spanning two parents is not duplicated); a source carries ``match_score``
only when it matched directly; a source's ``score`` combines its own match score
with its matched children's scores; a directly-matched source with no matching
children still appears with its own score; and an ancestor source that did not
match appears without a match score.
"""

from __future__ import annotations

from datetime import date

from floresu.embedding.config import EmbedItemKind
from floresu.profile.models import SourceKind
from floresu.search.fusion import FusedHit, ItemRef
from floresu.search.graph import BulletMeta, SourceMeta, WorklogMeta, assemble_graph


def _hit(kind: EmbedItemKind, item_id: int, score: float) -> FusedHit:
    return FusedHit(ref=ItemRef(kind, item_id), score=score)


_WL_META = {10: WorklogMeta(title="Shipped sharding", date=date(2024, 3, 1))}
_BL_META = {20: BulletMeta(text="Cut p99 latency 40%.")}
_SRC_META = {100: SourceMeta(kind=SourceKind.ROLE, label="Staff Engineer, Acme")}


def test_flat_hits_roll_into_source_worklog_and_bullet_nodes() -> None:
    graph = assemble_graph(
        [
            _hit(EmbedItemKind.WORKLOG, 10, 0.5),
            _hit(EmbedItemKind.BULLET, 20, 0.3),
            _hit(EmbedItemKind.SOURCE, 100, 0.2),
        ],
        source_meta=_SRC_META,
        worklog_meta=_WL_META,
        bullet_meta=_BL_META,
        bullet_worklog_edges=[(20, 10)],
        bullet_source_edges=[(20, 100)],
        worklog_source_edges=[(10, 100)],
    )
    assert [node.id for node in graph.worklog] == [10]
    assert graph.worklog[0].source_ids == [100]
    assert [node.id for node in graph.bullets] == [20]
    assert graph.bullets[0].worklog_ids == [10]
    assert graph.bullets[0].source_ids == [100]
    assert [node.id for node in graph.sources] == [100]


def test_a_bullet_spanning_two_parents_is_one_node() -> None:
    # The bullet frames two sources (ancestor grouping nodes) and two worklog
    # entries (both themselves hits); it must appear once with edges to both, never
    # duplicated per parent.
    graph = assemble_graph(
        [
            _hit(EmbedItemKind.BULLET, 20, 0.4),
            _hit(EmbedItemKind.WORKLOG, 10, 0.3),
            _hit(EmbedItemKind.WORKLOG, 11, 0.2),
        ],
        source_meta={
            100: SourceMeta(kind=SourceKind.ROLE, label="A"),
            101: SourceMeta(kind=SourceKind.PROJECT, label="B"),
        },
        worklog_meta={
            10: WorklogMeta(title="One", date=date(2024, 1, 1)),
            11: WorklogMeta(title="Two", date=date(2024, 2, 1)),
        },
        bullet_meta=_BL_META,
        bullet_worklog_edges=[(20, 10), (20, 11)],
        bullet_source_edges=[(20, 100), (20, 101)],
        worklog_source_edges=[],
    )
    assert len(graph.bullets) == 1
    assert graph.bullets[0].worklog_ids == [10, 11]
    assert graph.bullets[0].source_ids == [100, 101]


def test_a_directly_matched_source_with_no_children_scores_its_match_score() -> None:
    graph = assemble_graph(
        [_hit(EmbedItemKind.SOURCE, 100, 0.7)],
        source_meta=_SRC_META,
        worklog_meta={},
        bullet_meta={},
        bullet_worklog_edges=[],
        bullet_source_edges=[],
        worklog_source_edges=[],
    )
    assert len(graph.sources) == 1
    node = graph.sources[0]
    assert node.match_score == 0.7
    assert node.score == 0.7


def test_a_source_score_combines_match_score_with_matched_children() -> None:
    graph = assemble_graph(
        [
            _hit(EmbedItemKind.SOURCE, 100, 0.2),
            _hit(EmbedItemKind.WORKLOG, 10, 0.5),
            _hit(EmbedItemKind.BULLET, 20, 0.3),
        ],
        source_meta=_SRC_META,
        worklog_meta=_WL_META,
        bullet_meta=_BL_META,
        bullet_worklog_edges=[],
        bullet_source_edges=[(20, 100)],
        worklog_source_edges=[(10, 100)],
    )
    node = graph.sources[0]
    assert node.match_score == 0.2
    assert node.score == 0.2 + 0.5 + 0.3


def test_an_ancestor_source_that_did_not_match_has_no_match_score() -> None:
    # The source did not match the query (not a hit) but a matched worklog rolls up
    # to it, so it appears as a grouping node with no match_score and a score
    # derived purely from its matched child.
    graph = assemble_graph(
        [_hit(EmbedItemKind.WORKLOG, 10, 0.5)],
        source_meta=_SRC_META,
        worklog_meta=_WL_META,
        bullet_meta={},
        bullet_worklog_edges=[],
        bullet_source_edges=[],
        worklog_source_edges=[(10, 100)],
    )
    node = graph.sources[0]
    assert node.match_score is None
    assert node.score == 0.5


def test_an_edge_to_a_non_hit_worklog_is_dropped() -> None:
    # A hit bullet frames worklog 11, which did not match. 11 is not a worklog node,
    # so the bullet's worklog edge to it is scoped out (only hit worklogs are nodes).
    graph = assemble_graph(
        [_hit(EmbedItemKind.BULLET, 20, 0.4)],
        source_meta={},
        worklog_meta={},
        bullet_meta=_BL_META,
        bullet_worklog_edges=[(20, 11)],
        bullet_source_edges=[],
        worklog_source_edges=[],
    )
    assert graph.bullets[0].worklog_ids == []
    assert graph.worklog == []


def test_an_archived_ancestor_source_is_not_a_node() -> None:
    # The service omits archived sources from source_meta; the worklog_source edge
    # to the archived source is then scoped out and the source never appears.
    graph = assemble_graph(
        [_hit(EmbedItemKind.WORKLOG, 10, 0.5)],
        source_meta={},  # archived ancestor -> no metadata loaded
        worklog_meta=_WL_META,
        bullet_meta={},
        bullet_worklog_edges=[],
        bullet_source_edges=[],
        worklog_source_edges=[(10, 100)],
    )
    assert graph.sources == []
    assert graph.worklog[0].source_ids == []


def test_higher_scored_nodes_sort_first() -> None:
    graph = assemble_graph(
        [
            _hit(EmbedItemKind.WORKLOG, 10, 0.1),
            _hit(EmbedItemKind.WORKLOG, 11, 0.9),
        ],
        source_meta={},
        worklog_meta={
            10: WorklogMeta(title="low", date=date(2024, 1, 1)),
            11: WorklogMeta(title="high", date=date(2024, 2, 1)),
        },
        bullet_meta={},
        bullet_worklog_edges=[],
        bullet_source_edges=[],
        worklog_source_edges=[],
    )
    assert [node.id for node in graph.worklog] == [11, 10]
