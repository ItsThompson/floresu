"""External REST adapter for the live activity feed.

Two session-authed routes on the external app:

- ``GET /feed`` is the SSE stream. It resolves the caller's ``user_id`` from the
  session cookie, reads the ``Last-Event-ID`` the browser's ``EventSource`` sends
  on reconnect, and returns a ``text/event-stream`` that replays the gap from the
  Redis buffer and then streams live events with idle heartbeats.
- ``GET /feed/history`` is the initial page load: the recent audit rows,
  newest-first, that the client renders before opening the stream and dedups the
  live events against.

Both take no client-supplied id: the account is always the session-resolved
identity. Mounted on the external app only.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends
from starlette.requests import Request
from starlette.responses import StreamingResponse

from floresu.audit.schemas import AuditEntry
from floresu.audit.service import AuditService
from floresu.core.identity import resolve_user_pk
from floresu.feed.store import RedisFeedStore
from floresu.feed.stream import feed_frames
from floresu.feed.wiring import get_feed_store

# A FastAPI dependency resolving the request's ``user_id`` at the trust boundary
# (``require_user`` on the external app), injected so the router never hard-codes
# how identity is resolved.
Identity = Callable[..., Awaitable[str]]
# A FastAPI dependency that yields an AuditService for the request.
AuditServiceProvider = Callable[..., object]

# SSE response headers. ``no-cache`` and ``X-Accel-Buffering: no`` tell any proxy
# or edge not to buffer the stream, which together with the heartbeat frames keeps
# events flowing promptly rather than batching until the connection closes.
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _parse_last_event_id(request: Request) -> int | None:
    """The ``Last-Event-ID`` the browser resends on reconnect, or ``None``.

    A malformed value is treated as absent (full live stream, no replay) rather
    than an error: a bad header must not break the reconnect.
    """
    raw = request.headers.get("Last-Event-ID")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def create_feed_router(
    *, identity: Identity, audit_service_provider: AuditServiceProvider
) -> APIRouter:
    """Build the feed router, injecting identity and the audit service provider."""
    router = APIRouter(tags=["feed"])

    @router.get("/feed")
    async def stream_feed(
        request: Request,
        user_id: str = Depends(identity),
        store: RedisFeedStore = Depends(get_feed_store),
    ) -> StreamingResponse:
        last_event_id = _parse_last_event_id(request)
        frames = feed_frames(store, resolve_user_pk(user_id), last_event_id)
        return StreamingResponse(frames, media_type="text/event-stream", headers=_SSE_HEADERS)

    @router.get("/feed/history")
    async def feed_history(
        user_id: str = Depends(identity),
        service: AuditService = Depends(audit_service_provider),
    ) -> list[AuditEntry]:
        return await service.activity_feed(user_id)

    return router
