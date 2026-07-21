"""Lean wire schemas for the smoke tools (re-declared, not imported).

The MCP server ships as a separate image with no backend-code dependency, so it
re-declares the wire types it uses (the same "duplicated domain truth kept in
sync by contract" pattern as :mod:`floresu_mcp.config`'s header names). These two
shapes back the foundation's smoke tools and mirror the backend worklog wire
types; the full tool-surface schemas land with the read/write tools in later
tickets, and the cross-package contract tests (Ticket 22) keep them honest.

Inputs mirror the backend write body; outputs are lean summary-first projections.
IDs, timestamps, and server-owned fields are never accepted on a write.
"""

from __future__ import annotations

from datetime import date, datetime

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
