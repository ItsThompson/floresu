"""AuditService rules, tested sociably over an in-memory repository.

The real service maps a :class:`WriteEvent` to one audit row (resolving the actor,
storing no field-level diff) and reads the feed and per-item history newest-first.
The in-memory repository stands in for Postgres; everything else is the real code.
"""

from __future__ import annotations

import pytest

from floresu.audit.schemas import AuditEntry
from floresu.audit.service import AuditService
from floresu.core.actor import ActorType
from floresu.core.errors import Unauthorized
from floresu.core.events import Action
from tests.audit_fakes import InMemoryAuditRepository, agent_actor, build_write_event, human_actor


def _service() -> AuditService:
    return AuditService(InMemoryAuditRepository())


async def test_append_records_a_human_write_with_no_label() -> None:
    entry = await _service().append(
        build_write_event(user_id=7, actor=human_actor(), action=Action.CREATE)
    )
    assert entry.actor_type == ActorType.HUMAN
    assert entry.actor_label is None
    assert entry.action == "create"
    assert entry.id == 1  # first row gets the monotonic id 1
    assert entry.created_at is not None


async def test_append_records_a_named_agent_write() -> None:
    entry = await _service().append(build_write_event(actor=agent_actor("claude")))
    assert entry.actor_type == ActorType.AGENT
    assert entry.actor_label == "claude"


async def test_append_stores_action_summary_and_light_metadata_only() -> None:
    entry = await _service().append(
        build_write_event(
            action=Action.PROMOTE,
            summary="Promoted bullet to canonical",
            metadata={"scope": "everywhere", "revision": 3},
        )
    )
    assert entry.action == "promote"
    assert entry.summary == "Promoted bullet to canonical"
    assert entry.metadata == {"scope": "everywhere", "revision": 3}
    # No field-level diff is stored: the entry shape is exactly the lean record.
    assert set(AuditEntry.model_fields) == {
        "id",
        "actor_type",
        "actor_label",
        "entity_type",
        "entity_id",
        "action",
        "summary",
        "metadata",
        "created_at",
    }


async def test_each_append_produces_exactly_one_row() -> None:
    service = _service()
    await service.append(build_write_event(user_id=7))
    await service.append(build_write_event(user_id=7))
    assert len(await service.activity_feed("7")) == 2


async def test_activity_feed_is_newest_first_for_the_user() -> None:
    service = _service()
    first = await service.append(build_write_event(user_id=7, action=Action.CREATE))
    second = await service.append(build_write_event(user_id=7, action=Action.UPDATE))
    third = await service.append(build_write_event(user_id=7, action=Action.ARCHIVE))

    feed = await service.activity_feed("7")
    assert [entry.id for entry in feed] == [third.id, second.id, first.id]


async def test_activity_feed_is_scoped_to_the_user() -> None:
    service = _service()
    await service.append(build_write_event(user_id=7))
    await service.append(build_write_event(user_id=8))

    feed = await service.activity_feed("7")
    assert len(feed) == 1


async def test_item_history_filters_to_one_entity_newest_first() -> None:
    service = _service()
    # Two writes on the target item, interleaved with an unrelated item.
    await service.append(build_write_event(user_id=7, entity_type="bullet", entity_id=5))
    await service.append(build_write_event(user_id=7, entity_type="worklog", entity_id=99))
    latest = await service.append(
        build_write_event(user_id=7, entity_type="bullet", entity_id=5, action=Action.UPDATE)
    )

    history = await service.item_history("7", "bullet", 5)
    assert [entry.id for entry in history] == [latest.id, 1]
    assert all(entry.entity_type == "bullet" and entry.entity_id == 5 for entry in history)


async def test_item_history_reflects_both_human_and_agent_writes() -> None:
    service = _service()
    await service.append(
        build_write_event(user_id=7, entity_type="resume", entity_id=3, actor=human_actor())
    )
    await service.append(
        build_write_event(user_id=7, entity_type="resume", entity_id=3, actor=agent_actor("claude"))
    )

    history = await service.item_history("7", "resume", 3)
    assert {entry.actor_type for entry in history} == {ActorType.HUMAN, ActorType.AGENT}


async def test_reads_reject_a_malformed_user_id_with_unauthorized() -> None:
    service = _service()
    await service.append(build_write_event(user_id=7))
    with pytest.raises(Unauthorized):
        await service.activity_feed("not-a-number")
    with pytest.raises(Unauthorized):
        await service.item_history("not-a-number", "worklog", 100)


async def test_activity_feed_respects_the_limit() -> None:
    service = _service()
    for _ in range(5):
        await service.append(build_write_event(user_id=7))
    assert len(await service.activity_feed("7", limit=2)) == 2
