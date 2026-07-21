"""Shared DB helper: map a unique-constraint breach to a recoverable Conflict.

Several domains carry a ``UNIQUE`` constraint whose breach must read as a
model-recoverable :class:`Conflict` rather than a 500: a curated profile name or
label, a resume's 1:1 job-application link, a resume revision's ``(resume_id,
revision_no)`` primary key under a genuine concurrent write. Rather than repeat the
mapping per service, this one async context manager wraps the write: the
``transaction`` boundary rolls the write back and re-raises the ``IntegrityError``,
and this maps a unique-violation to a :class:`Conflict` carrying a caller-supplied
message. A concurrent duplicate (records are written by both the human and the
agent) therefore never surfaces as a 500. A non-unique integrity error still
propagates unchanged.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.exc import IntegrityError

from floresu.core.db import is_unique_violation
from floresu.core.errors import Conflict


@asynccontextmanager
async def conflict_on_duplicate(message: str) -> AsyncIterator[None]:
    """Wrap a write so a unique-constraint breach becomes a :class:`Conflict`."""
    try:
        yield
    except IntegrityError as exc:
        if is_unique_violation(exc):
            raise Conflict(message) from exc
        raise
