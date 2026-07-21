"""Load the graph inputs for a hit set: node metadata and the three provenance joins.

After fusion picks the hit set, the scored DAG needs each hit's display metadata
and the edges connecting the hits. This module reads them from Postgres, scoped to
the owner, and rolls in the (non-archived) ancestor sources that matched hits
belong to, so the pure :func:`floresu.search.graph.assemble_graph` can group the
hits under their sources. It performs no fusion and no ranking: just the scoped
reads the graph assembly consumes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import InstrumentedAttribute

from floresu.library.models import Bulletpoint, BulletSource, BulletWorklog
from floresu.profile.models import Source
from floresu.search.graph import BulletMeta, SourceMeta, WorklogMeta
from floresu.worklog.models import WorklogEntry, WorklogSource

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class GraphInputs:
    """Node metadata and the three provenance joins for a hit set (owner-scoped)."""

    source_meta: dict[int, SourceMeta]
    worklog_meta: dict[int, WorklogMeta]
    bullet_meta: dict[int, BulletMeta]
    bullet_worklog_edges: list[tuple[int, int]]
    bullet_source_edges: list[tuple[int, int]]
    worklog_source_edges: list[tuple[int, int]]


async def load_graph_inputs(
    session: AsyncSession,
    user_id: int,
    worklog_ids: set[int],
    bullet_ids: set[int],
    source_ids: set[int],
) -> GraphInputs:
    """Read the node metadata and the three provenance edges for a hit set."""
    worklog_meta = await _worklog_meta(session, user_id, worklog_ids)
    bullet_meta = await _bullet_meta(session, user_id, bullet_ids)
    bullet_worklog_edges = await _edges(
        session,
        BulletWorklog.bullet_id,
        BulletWorklog.worklog_id,
        BulletWorklog.bullet_id,
        bullet_ids,
    )
    bullet_source_edges = await _edges(
        session, BulletSource.bullet_id, BulletSource.source_id, BulletSource.bullet_id, bullet_ids
    )
    worklog_source_edges = await _edges(
        session,
        WorklogSource.worklog_id,
        WorklogSource.source_id,
        WorklogSource.worklog_id,
        worklog_ids,
    )
    # Node sources are the direct source hits plus the ancestors matched hits roll
    # up to; archived ancestors are dropped by the owner-scoped metadata read.
    ancestor_source_ids = (
        source_ids
        | {source_id for _b, source_id in bullet_source_edges}
        | {source_id for _w, source_id in worklog_source_edges}
    )
    source_meta = await _source_meta(session, user_id, ancestor_source_ids)
    return GraphInputs(
        source_meta=source_meta,
        worklog_meta=worklog_meta,
        bullet_meta=bullet_meta,
        bullet_worklog_edges=bullet_worklog_edges,
        bullet_source_edges=bullet_source_edges,
        worklog_source_edges=worklog_source_edges,
    )


async def _worklog_meta(
    session: AsyncSession, user_id: int, ids: set[int]
) -> dict[int, WorklogMeta]:
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(WorklogEntry.id, WorklogEntry.title, WorklogEntry.entry_date).where(
                WorklogEntry.user_id == user_id, WorklogEntry.id.in_(ids)
            )
        )
    ).all()
    return {row.id: WorklogMeta(title=row.title, date=row.entry_date) for row in rows}


async def _bullet_meta(session: AsyncSession, user_id: int, ids: set[int]) -> dict[int, BulletMeta]:
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(Bulletpoint.id, Bulletpoint.text).where(
                Bulletpoint.user_id == user_id, Bulletpoint.id.in_(ids)
            )
        )
    ).all()
    return {row.id: BulletMeta(text=row.text) for row in rows}


async def _source_meta(session: AsyncSession, user_id: int, ids: set[int]) -> dict[int, SourceMeta]:
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(Source.id, Source.kind, Source.display_label).where(
                Source.user_id == user_id,
                Source.id.in_(ids),
                Source.archived_at.is_(None),
            )
        )
    ).all()
    return {row.id: SourceMeta(kind=row.kind, label=row.display_label) for row in rows}


async def _edges(
    session: AsyncSession,
    parent_col: InstrumentedAttribute[int],
    child_col: InstrumentedAttribute[int],
    scope_col: InstrumentedAttribute[int],
    parent_ids: set[int],
) -> list[tuple[int, int]]:
    """Load ``(parent, child)`` edge rows for a set of parent ids, or none if empty."""
    if not parent_ids:
        return []
    rows = (
        await session.execute(select(parent_col, child_col).where(scope_col.in_(parent_ids)))
    ).all()
    return [(row[0], row[1]) for row in rows]
