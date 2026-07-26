"""The internal (agent) app wires the SSE feed publish, and only the publish.

Docker-less composition-root assertions. The internal app must register the same
``build_sse_feed_consumer`` the external app does, over a Redis-backed feed store,
so an agent write fans out to the open feed identically to a human write. It must
NOT gain the read side: it does not serve ``GET /feed`` and does not set
``FEED_STORE_ATTR`` on ``app.state`` (the stream route stays external-only). The
behavioral proof over real Redis lives in ``test_internal_feed_integration.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.api_internal.main import app as internal_app
from floresu.api_internal.main import create_internal_app
from floresu.core.route_registry import mounted_product_routes
from floresu.feed.store import RedisFeedStore
from floresu.feed.wiring import FEED_STORE_ATTR

if TYPE_CHECKING:
    import pytest

    from floresu.core.events import PostCommitConsumer, RecordedWrite


def test_internal_app_registers_the_sse_feed_consumer(monkeypatch: pytest.MonkeyPatch) -> None:
    # The composition root must build a RedisFeedStore and register its SSE consumer
    # as a post-commit side channel. Spy the consumer factory so dropping the wiring
    # fails here without needing Redis.
    stores: list[object] = []

    def _spy(store: RedisFeedStore) -> PostCommitConsumer:
        stores.append(store)

        async def _consume(_recorded: RecordedWrite) -> None:  # pragma: no cover - not invoked
            return None

        return _consume

    monkeypatch.setattr("floresu.api_internal.main.build_sse_feed_consumer", _spy)

    create_internal_app()

    assert len(stores) == 1, "internal app must register exactly one SSE feed consumer"
    assert isinstance(stores[0], RedisFeedStore)


def test_internal_app_does_not_expose_a_streaming_feed_store() -> None:
    # The internal app only publishes; the SSE stream route is external-only, so it
    # never resolves a feed store off app.state.
    assert not hasattr(internal_app.state, FEED_STORE_ATTR)


def test_internal_app_does_not_serve_the_feed_routes() -> None:
    paths = {key.path for key in mounted_product_routes(internal_app)}
    assert "/feed" not in paths
    assert "/feed/history" not in paths
    assert "/feed/history/{entity_type}/{entity_id}" not in paths
