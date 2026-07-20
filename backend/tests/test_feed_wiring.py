"""The feed side channel and entry projection (:mod:`floresu.feed.wiring`).

Unit-level: a fake store records what the post-commit consumer publishes, so the
recorded-write -> audit-entry projection and the per-user channel routing are
asserted without Redis.
"""

from __future__ import annotations

from floresu.core.actor import ActorType
from floresu.feed.wiring import build_sse_feed_consumer
from tests.audit_fakes import build_recorded_write


class _RecordingStore:
    def __init__(self) -> None:
        self.published: list[tuple[int, object]] = []

    async def publish(self, user_id: int, entry: object) -> None:
        self.published.append((user_id, entry))


async def test_consumer_publishes_the_recorded_write_to_the_owners_channel() -> None:
    store = _RecordingStore()
    consumer = build_sse_feed_consumer(store)  # type: ignore[arg-type]
    recorded = build_recorded_write(audit_id=7, user_id=42, entity_type="bullet", entity_id=3)

    await consumer(recorded)

    assert len(store.published) == 1
    user_id, entry = store.published[0]
    assert user_id == 42
    # The wire entry carries the durable audit id and the write's fields.
    assert entry.id == 7  # type: ignore[attr-defined]
    assert entry.entity_type == "bullet"  # type: ignore[attr-defined]
    assert entry.entity_id == 3  # type: ignore[attr-defined]
    assert entry.actor_type == ActorType.HUMAN  # type: ignore[attr-defined]


async def test_consumer_projects_a_named_agent_actor() -> None:
    store = _RecordingStore()
    consumer = build_sse_feed_consumer(store)  # type: ignore[arg-type]
    recorded = build_recorded_write(audit_id=9, user_id=1)
    # Swap the human default for a named agent to check the label carries through.
    recorded = recorded.model_copy(
        update={"event": recorded.event.model_copy(update={"actor": _agent()})}
    )

    await consumer(recorded)

    _, entry = store.published[0]
    assert entry.actor_type == ActorType.AGENT  # type: ignore[attr-defined]
    assert entry.actor_label == "claude"  # type: ignore[attr-defined]


def _agent() -> object:
    from floresu.core.actor import Actor

    return Actor(type=ActorType.AGENT, label="claude")
