"""Unit tests for the pure provenance-DAG assembly module.

Pure: edges plus node-id sets in, grouped adjacency out. Asserts the three joins
are grouped by parent, scoped strictly to the given id sets, and that each node
appears once (a bullet framing two parents is one key with two children, a node
shared by two parents is not duplicated as a node).
"""

from __future__ import annotations

from floresu.library.provenance import build_provenance_dag


def test_groups_the_three_joins_by_parent() -> None:
    dag = build_provenance_dag(
        bullet_ids=[1],
        worklog_ids=[10],
        source_ids=[100],
        bullet_worklog_edges=[(1, 10)],
        bullet_source_edges=[(1, 100)],
        worklog_source_edges=[(10, 100)],
    )
    assert dag.bullet_worklog == {1: [10]}
    assert dag.bullet_source == {1: [100]}
    assert dag.worklog_source == {10: [100]}


def test_a_bullet_spanning_two_parents_is_one_key_with_sorted_children() -> None:
    # A bullet framing two worklog entries and two sources appears once per join,
    # each with its children unique and sorted (never a duplicated node).
    dag = build_provenance_dag(
        bullet_ids=[1],
        worklog_ids=[10, 11],
        source_ids=[100, 101],
        bullet_worklog_edges=[(1, 11), (1, 10), (1, 10)],
        bullet_source_edges=[(1, 101), (1, 100)],
        worklog_source_edges=[],
    )
    assert dag.bullet_worklog == {1: [10, 11]}
    assert dag.bullet_source == {1: [100, 101]}


def test_a_node_shared_by_two_parents_is_not_duplicated() -> None:
    # One source framed by two bullets and one worklog appears under each parent's
    # list, but the node itself (id 100) is never emitted as a standalone duplicate.
    dag = build_provenance_dag(
        bullet_ids=[1, 2],
        worklog_ids=[10],
        source_ids=[100],
        bullet_worklog_edges=[],
        bullet_source_edges=[(1, 100), (2, 100)],
        worklog_source_edges=[(10, 100)],
    )
    assert dag.bullet_source == {1: [100], 2: [100]}
    assert dag.worklog_source == {10: [100]}


def test_edges_are_scoped_to_the_given_id_sets() -> None:
    # An edge is kept only when both endpoints are in the sets: the (1, 11) worklog
    # edge and the (2, 100) source edge are dropped because 11 and 2 are out of set.
    dag = build_provenance_dag(
        bullet_ids=[1],
        worklog_ids=[10],
        source_ids=[100],
        bullet_worklog_edges=[(1, 10), (1, 11)],
        bullet_source_edges=[(1, 100), (2, 100)],
        worklog_source_edges=[(10, 100)],
    )
    assert dag.bullet_worklog == {1: [10]}
    assert dag.bullet_source == {1: [100]}
    assert dag.worklog_source == {10: [100]}


def test_empty_inputs_yield_empty_adjacency() -> None:
    dag = build_provenance_dag(
        bullet_ids=[],
        worklog_ids=[],
        source_ids=[],
        bullet_worklog_edges=[],
        bullet_source_edges=[],
        worklog_source_edges=[],
    )
    assert dag.bullet_worklog == {}
    assert dag.bullet_source == {}
    assert dag.worklog_source == {}


def test_a_bullet_with_no_edges_does_not_appear() -> None:
    # A hit bullet with both joins empty is simply absent from the adjacency maps;
    # the caller still lists it as an (ungrouped) node from its own id set.
    dag = build_provenance_dag(
        bullet_ids=[1, 2],
        worklog_ids=[10],
        source_ids=[100],
        bullet_worklog_edges=[(1, 10)],
        bullet_source_edges=[(1, 100)],
        worklog_source_edges=[],
    )
    assert 2 not in dag.bullet_worklog
    assert 2 not in dag.bullet_source
