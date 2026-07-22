"""Wire schemas for worklog: the write body, the read shapes, and the tag read.

A write (:class:`WorklogWrite`) carries a required title and date, an optional
description, and the entry's full tag and source-attachment lists. The same shape
backs create and full-representation update: setting the ``tags`` list is how a
tag is added (a new label) or removed (an omitted label), and setting
``source_ids`` is how attachments are added or removed. IDs, timestamps, and the
content hash are server-owned and never accepted on a write.

Reads come in two shapes. A :class:`WorklogSummary` carries an entry with its tag
labels and attached source ids for the timeline; a :class:`WorklogRecord` adds the
``bullet_ids`` of the canonical bulletpoints that frame the entry. Tag color is
never carried: it is derived from the label by the shared ``colorForName`` utility
wherever a tag is rendered.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from floresu.worklog.models import Tag, WorklogEntry


class WorklogWrite(BaseModel):
    """The create/update body: required title + date; optional description, tags, sources."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    entry_date: date
    description: str | None = None
    # Free-text labels; a new label creates a tag, an existing one is reused. The
    # service normalizes (trims, drops blanks, de-duplicates) before reconciling.
    tags: list[str] = Field(default_factory=list)
    # Attached source ids; zero, one, or many. The service rejects any id the user
    # does not own, so an entry can never attach a foreign source.
    source_ids: list[int] = Field(default_factory=list)


class TagMutation(BaseModel):
    """A single tag label to add to or remove from a worklog entry.

    The partial-tag route (``POST /worklog/{id}/tags``) carries this instead of a
    full :class:`WorklogWrite`, so a caller can reconcile one label without
    resubmitting the entry's whole representation. The service normalizes the
    label (trim, reject blank) and the router dispatches on ``action`` to
    ``add_tag`` / ``remove_tag``.
    """

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    action: Literal["add", "remove"]


class WorklogSummary(BaseModel):
    """A worklog entry with its tags and attached sources (the timeline row)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    entry_date: date
    description: str | None
    tags: list[str]
    source_ids: list[int]
    archived_at: datetime | None


class WorklogRecord(WorklogSummary):
    """A single entry, adding the bulletpoints that frame it (provenance)."""

    # The canonical bulletpoints whose ``bullet_worklog`` edges point at this entry
    # (archived bullets excluded); empty for an entry no bullet frames.
    bullet_ids: list[int]


class TagRead(BaseModel):
    """A tag for the reuse list; color is derived from the label, not carried."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str


def to_summary(entry: WorklogEntry, tags: list[str], source_ids: list[int]) -> WorklogSummary:
    """Project an entry plus its resolved edge lists onto the timeline read shape."""
    return WorklogSummary(
        id=entry.id,
        title=entry.title,
        entry_date=entry.entry_date,
        description=entry.description,
        tags=tags,
        source_ids=source_ids,
        archived_at=entry.archived_at,
    )


def to_record(
    entry: WorklogEntry, tags: list[str], source_ids: list[int], bullet_ids: list[int]
) -> WorklogRecord:
    """Add the framing bullet ids to the summary projection for a single-entry read.

    The summary projection is single-sourced through :func:`to_summary`, so adding
    a common field does not need a matching edit here.
    """
    return WorklogRecord(**to_summary(entry, tags, source_ids).model_dump(), bullet_ids=bullet_ids)


def to_tag_read(tag: Tag) -> TagRead:
    """Project a ``tags`` ORM row onto the reuse read shape."""
    return TagRead.model_validate(tag)
