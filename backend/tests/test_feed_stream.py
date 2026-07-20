"""SSE frame formatting for the feed stream (:mod:`floresu.feed.stream`).

Unit-level: a fake store supplies the replay gap and a finite live sequence, so the
frame ordering (replay first, then live), the ``id:``/``data:`` framing, and the
idle heartbeat are asserted without Redis.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from floresu.feed.stream import HEARTBEAT_FRAME, event_frame, feed_frames
from tests.audit_fakes import build_audit_entry

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from floresu.audit.schemas import AuditEntry
    from floresu.feed.store import RedisFeedStore


class _FakeStore:
    """A feed store with canned replay and a finite live sequence for the stream."""

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


def _as_store(fake: _FakeStore) -> RedisFeedStore:
    return cast("RedisFeedStore", fake)


async def _collect(frames: AsyncIterator[str]) -> list[str]:
    return [frame async for frame in frames]


def test_event_frame_carries_the_id_and_json_payload() -> None:
    entry = build_audit_entry(id=42, entity_type="worklog", entity_id=7)
    frame = event_frame(entry)
    assert frame.startswith("id: 42\ndata: ")
    assert frame.endswith("\n\n")
    assert '"id":42' in frame
    assert '"entity_type":"worklog"' in frame


async def test_replayed_gap_is_emitted_before_live_events() -> None:
    replay = [build_audit_entry(id=6), build_audit_entry(id=7)]
    live = [build_audit_entry(id=8)]
    store = _FakeStore(replay=replay, live=live)

    frames = await _collect(feed_frames(_as_store(store), user_id=1, last_event_id=5))

    assert store.replay_since_args == (1, 5)
    assert [frame.split("\n", 1)[0] for frame in frames] == ["id: 6", "id: 7", "id: 8"]


async def test_no_replay_when_there_is_no_last_event_id() -> None:
    store = _FakeStore(replay=[build_audit_entry(id=99)], live=[build_audit_entry(id=8)])

    frames = await _collect(feed_frames(_as_store(store), user_id=1, last_event_id=None))

    # replay_since is never consulted; only the live event is framed.
    assert store.replay_since_args is None
    assert [frame.split("\n", 1)[0] for frame in frames] == ["id: 8"]


async def test_idle_ticks_emit_a_heartbeat_comment_frame() -> None:
    store = _FakeStore(replay=[], live=[None, build_audit_entry(id=8), None])

    frames = await _collect(feed_frames(_as_store(store), user_id=1, last_event_id=None))

    assert frames[0] == HEARTBEAT_FRAME
    assert frames[1].startswith("id: 8")
    assert frames[2] == HEARTBEAT_FRAME
