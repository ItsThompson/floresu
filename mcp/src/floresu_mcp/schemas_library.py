"""Lean library-bullet read schema (re-declared, not imported).

``bullet_list`` and ``bullet_get`` return a canonical bulletpoint with its
resolved provenance edges (the ``source_ids`` it frames directly and the
``worklog_ids`` it frames), its ``revision`` token, and ``used_in_count`` (how
many resumes reference it). The read shape ignores unrecognized fields so a
backend addition never breaks it. The cross-package contract tests (Ticket 22)
keep the mirror honest.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BulletpointRecord(BaseModel):
    """A canonical bulletpoint with its resolved provenance edges and usage count."""

    model_config = ConfigDict(extra="ignore")

    id: int
    text: str
    source_ids: list[int]
    worklog_ids: list[int]
    used_in_count: int
    revision: int
    archived_at: datetime | None = None
