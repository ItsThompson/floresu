"""External feed router (:mod:`floresu.feed.api`): the SSE stream and initial load.

Sociable API-level tests over a minimal app that mounts the real router with an
injected identity, a fake feed store (finite live sequence so the stream
terminates), and the real :class:`AuditService` over the in-memory repository for
the history read. Asserts the SSE content type and framing, ``Last-Event-ID``
parsing, and the newest-first history payload.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI
from starlette.testclient import TestClient

from floresu.audit.service import AuditService
from floresu.feed.api import create_feed_router
from floresu.feed.wiring import FEED_STORE_ATTR
from tests.audit_fakes import InMemoryAuditRepository, build_audit_entry, build_write_event

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from floresu.audit.schemas import AuditEntry


class _FakeStore:
    def __init__(self, *, replay: Sequence[AuditEntry], live: Sequence[AuditEntry | None]) -> None:
        self._replay = replay
        self._live = live
        self.replay_since_args: tuple[int, int] | None = None

    async def replay_since(self, user_id: int, last_event_id: int) -> list[AuditEntry]:
        self.replay_since_args = (user_id, last_event_id)
        return list(self._replay)

    async def listen(
        self, user_id: int, *, heartbeat_timeout: float
    ) -> AsyncIterator[AuditEntry | None]:
        for item in self._live:
            yield item


def _build_app(store: _FakeStore, service: AuditService) -> FastAPI:
    async def identity() -> str:
        return "1"

    def audit_provider() -> AuditService:
        return service

    app = FastAPI()
    app.include_router(create_feed_router(identity=identity, audit_service_provider=audit_provider))
    setattr(app.state, FEED_STORE_ATTR, store)
    return app


def test_feed_streams_event_source_frames_and_replays_the_gap() -> None:
    store = _FakeStore(replay=[build_audit_entry(id=6)], live=[build_audit_entry(id=7)])
    service = AuditService(InMemoryAuditRepository())  # unused by /feed
    client = TestClient(_build_app(store, service))

    response = client.get("/feed", headers={"Last-Event-ID": "5"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    # The reconnect id was parsed and used to replay the gap before the live event.
    assert store.replay_since_args == (1, 5)
    assert "id: 6" in response.text
    assert "id: 7" in response.text
    assert response.text.index("id: 6") < response.text.index("id: 7")


def test_feed_without_last_event_id_skips_replay() -> None:
    store = _FakeStore(replay=[build_audit_entry(id=6)], live=[build_audit_entry(id=7)])
    service = AuditService(InMemoryAuditRepository())
    client = TestClient(_build_app(store, service))

    response = client.get("/feed")

    assert response.status_code == 200
    assert store.replay_since_args is None
    assert "id: 6" not in response.text
    assert "id: 7" in response.text


def test_feed_history_returns_recent_rows_newest_first() -> None:
    repo = InMemoryAuditRepository()
    service = AuditService(repo)
    store = _FakeStore(replay=[], live=[])
    client = TestClient(_build_app(store, service))

    import asyncio

    async def seed() -> None:
        await service.append(build_write_event(user_id=1, entity_type="worklog", entity_id=10))
        await service.append(build_write_event(user_id=1, entity_type="worklog", entity_id=11))

    asyncio.run(seed())

    response = client.get("/feed/history")

    assert response.status_code == 200
    rows = response.json()
    assert [row["entity_id"] for row in rows] == [11, 10]  # newest-first
    assert rows[0]["id"] > rows[1]["id"]
