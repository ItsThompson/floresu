"""Compose the write-event publisher with the audit consumer.

Keeps the "which consumers are registered" decision at the composition root and
out of the seam and services. The audit append is always the transactional
consumer, so every write is recorded in its own transaction. Later slices pass the
SSE and embed side channels as ``best_effort`` from the app entrypoint, without
editing the seam or any service.

The transactional consumer builds a request-scoped audit service over the caller's
session, so the audit row enlists in the content write's transaction, and returns
the :class:`RecordedWrite` it minted so post-commit side channels can publish the
durable record's id.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.audit.repository import SqlAlchemyAuditRepository
from floresu.audit.service import AuditService
from floresu.core.events import RecordedWrite, TransactionalConsumer, WriteEventPublisher
from floresu.core.providers import ServiceProvider, session_provider

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.core.events import PostCommitConsumer, WriteEvent


def build_audit_consumer() -> TransactionalConsumer:
    """The transactional consumer that appends one audit row per write.

    Returns the :class:`RecordedWrite` carrying the row's minted monotonic id, so
    the publisher can hand it to the post-commit side channels (the SSE feed).
    """

    async def consume(session: AsyncSession, event: WriteEvent) -> RecordedWrite:
        service = AuditService(SqlAlchemyAuditRepository(session))
        entry = await service.append(event)
        return RecordedWrite(event=event, audit_id=entry.id, created_at=entry.created_at)

    return consume


def build_write_event_publisher(
    *, post_commit: Sequence[PostCommitConsumer] = ()
) -> WriteEventPublisher:
    """Compose the publisher: audit as the transactional consumer, side channels post-commit."""
    return WriteEventPublisher(transactional=[build_audit_consumer()], post_commit=post_commit)


def build_audit_service_provider() -> ServiceProvider[AuditService]:
    """A FastAPI dependency that builds a request-scoped :class:`AuditService`.

    Backs the read endpoints (the activity-feed initial load; the future item
    history) over a per-request session, mirroring the accounts service provider.
    """
    return session_provider(lambda session: AuditService(SqlAlchemyAuditRepository(session)))
