"""Compose the OAuth AS dependency graph for the external app.

Declares how the request-scoped OAuth services are built and defers the wiring
mechanics (resolving the session) to :func:`session_provider`. The signing key
set and access-token codec are process-wide singletons captured by the ``build``
closures, mirroring the accounts wiring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.core.providers import ServiceProvider, session_provider
from floresu.oauth.authorization import AuthorizationService
from floresu.oauth.repository import SqlAlchemyOAuthRepository
from floresu.oauth.token_exchange import TokenService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.oauth.config import OAuthConfig
    from floresu.oauth.tokens import AccessTokenCodec


def build_authorization_service_provider(
    config: OAuthConfig,
) -> ServiceProvider[AuthorizationService]:
    """A FastAPI dependency that builds a request-scoped :class:`AuthorizationService`."""
    return session_provider(
        lambda session: AuthorizationService(SqlAlchemyOAuthRepository(session), config)
    )


def build_token_service(
    session: AsyncSession, config: OAuthConfig, codec: AccessTokenCodec
) -> TokenService:
    """Bind a :class:`TokenService` over a session.

    Shared by the request-scoped provider and the background client-cleanup sweep
    (:mod:`floresu.oauth.cleanup`), so the two never diverge in how the service is
    composed.
    """
    return TokenService(SqlAlchemyOAuthRepository(session), config, codec)


def build_token_service_provider(
    config: OAuthConfig, codec: AccessTokenCodec
) -> ServiceProvider[TokenService]:
    """A FastAPI dependency that builds a request-scoped :class:`TokenService`."""
    return session_provider(lambda session: build_token_service(session, config, codec))
