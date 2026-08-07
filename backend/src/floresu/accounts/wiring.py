"""Compose the accounts dependency graph for the external app.

Declares how a request-scoped :class:`AccountService` is built and defers the
wiring mechanics (resolving the session) to :func:`session_provider`. The hasher
and codec are process-wide singletons captured by the ``build`` closure.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.accounts.notifications import (
    NULL_EVENT_PUBLISHER,
    BestEffortEventPublisher,
    DiscordUserRegisteredHandler,
    EventPublisher,
)
from floresu.accounts.repository import SqlAlchemyAccountRepository
from floresu.accounts.service import AccountService
from floresu.core.providers import ServiceProvider, session_provider

if TYPE_CHECKING:
    from floresu.accounts.passwords import PasswordHasher
    from floresu.accounts.tokens import SessionTokenCodec
    from floresu.core.settings import AppSettings


def build_event_publisher(settings: AppSettings) -> EventPublisher:
    """Build process-wide account-registration event delivery for the external app."""
    if not settings.discord_webhook_url.get_secret_value():
        return NULL_EVENT_PUBLISHER
    return BestEffortEventPublisher([DiscordUserRegisteredHandler(settings.discord_webhook_url)])


def build_account_service_provider(
    hasher: PasswordHasher,
    codec: SessionTokenCodec,
    event_publisher: EventPublisher = NULL_EVENT_PUBLISHER,
) -> ServiceProvider[AccountService]:
    """A FastAPI dependency that builds a request-scoped :class:`AccountService`."""
    return session_provider(
        lambda session: AccountService(
            SqlAlchemyAccountRepository(session), hasher, codec, event_publisher=event_publisher
        )
    )
