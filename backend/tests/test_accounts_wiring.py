"""Accounts wiring."""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.accounts.notifications import BestEffortEventPublisher, NullEventPublisher
from floresu.accounts.wiring import build_event_publisher

if TYPE_CHECKING:
    from tests.conftest import MakeSettings


def test_event_publisher_is_null_without_a_webhook(make_settings: MakeSettings) -> None:
    publisher = build_event_publisher(make_settings(discord_webhook_url=""))
    assert isinstance(publisher, NullEventPublisher)


def test_event_publisher_is_best_effort_with_a_webhook(make_settings: MakeSettings) -> None:
    settings = make_settings(discord_webhook_url="https://discord.test/webhooks/123/secret")
    publisher = build_event_publisher(settings)
    assert isinstance(publisher, BestEffortEventPublisher)
