"""Lean worklog + tag wire schemas (re-declared, not imported).

The MCP server ships as a separate image with no backend-code dependency, so it
re-declares the wire types it uses (the same "duplicated domain truth kept in
sync by contract" pattern as :mod:`floresu_mcp.config`'s header names). The
per-domain read shapes live in sibling ``schemas_*`` modules; this module holds
the worklog + tag shapes the worklog tools use. The cross-package contract tests
(Ticket 22) keep every mirror honest.

Inputs mirror the backend write body; outputs are lean summary-first projections
that ignore unrecognized fields, so a backend addition never breaks a read. IDs,
timestamps, and server-owned fields are never accepted on a write.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WorklogEntryInput(BaseModel):
    """The worklog create body: required title + date; optional description, tags, sources."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    entry_date: date
    description: str | None = None
    # Free-text labels; a new label creates a tag, an existing one is reused.
    tags: list[str] = Field(default_factory=list)
    # Attached source ids; the backend rejects any id the user does not own.
    source_ids: list[int] = Field(default_factory=list)


class WorklogTagInput(BaseModel):
    """The partial-tag body: one label to add or remove on an entry.

    Backs ``worklog_tag``, the single-label counterpart to the full-representation
    ``tags`` list on create/update. The entry id is a tool-function argument (a
    backend path parameter), not a body field, matching :class:`WorklogEntryInput`
    / ``worklog_update``. The pair is sent verbatim to ``POST /worklog/{id}/tags``;
    the backend normalizes the label and dispatches on ``action``.
    """

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    action: Literal["add", "remove"]


class WorklogEntrySummary(BaseModel):
    """A worklog entry projected to the lean timeline shape the agent receives."""

    model_config = ConfigDict(extra="ignore")

    id: int
    title: str
    entry_date: date
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    source_ids: list[int] = Field(default_factory=list)
    archived_at: datetime | None = None


class WorklogEntryRecord(WorklogEntrySummary):
    """A single worklog entry, adding the canonical bullets that frame it.

    ``worklog_get`` returns this: the timeline summary (its tags and attached
    source ids) plus the ids of the canonical bullets whose provenance edges point
    at the entry, so the agent can trace an entry to its library accomplishments.
    """

    bullet_ids: list[int] = Field(default_factory=list)


class Tag(BaseModel):
    """An existing tag label for reuse. ``list_tags`` returns these so the agent
    reuses a label rather than minting a near-duplicate; color is derived from the
    label wherever a tag is rendered, never carried here."""

    model_config = ConfigDict(extra="ignore")

    id: int
    label: str
