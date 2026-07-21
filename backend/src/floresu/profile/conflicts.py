"""Shared profile helper: map a unique-constraint breach to a recoverable Conflict.

The curated profile entities (skills, identity variants) each carry a per-user
``UNIQUE`` constraint (a skill name, a variant label). A create or rename onto a
name another row already holds breaches that constraint. Rather than repeat the
mapping in each service, this one async context manager wraps the write: the
``transaction`` boundary rolls the write back and re-raises the ``IntegrityError``,
and this maps it to a model-recoverable :class:`Conflict`. A concurrent duplicate
(these entities are written by both the human and the agent) therefore never
surfaces as a 500. A non-unique integrity error still propagates unchanged.
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
