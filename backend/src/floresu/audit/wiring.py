"""Compose the write-event publisher with the audit consumer.

Keeps the "which consumers are registered" decision at the composition root and
out of the seam and services. The audit append is always the transactional
consumer, so every write is recorded in its own transaction. Later slices pass the
SSE and embed side channels as ``best_effort`` from the app entrypoint, without
editing the seam or any service.

The transactional consumer builds a request-scoped audit service over the caller's
session, so the audit row enlists in the content write's transaction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.audit.repository import SqlAlchemyAuditRepository
from floresu.audit.service import AuditService
from floresu.core.events import TransactionalConsumer, WriteEventPublisher

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.core.events import BestEffortConsumer, WriteEvent


def build_audit_consumer() -> TransactionalConsumer:
    """The transactional consumer that appends one audit row per write."""

    async def consume(session: AsyncSession, event: WriteEvent) -> None:
        service = AuditService(SqlAlchemyAuditRepository(session))
        await service.append(event)

    return consume


def build_write_event_publisher(
    *, best_effort: Sequence[BestEffortConsumer] = ()
) -> WriteEventPublisher:
    """Compose the publisher: audit as the transactional consumer, side channels best-effort."""
    return WriteEventPublisher(transactional=[build_audit_consumer()], best_effort=best_effort)
