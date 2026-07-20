"""Compose the accounts dependency graph for the external app.

Keeps the wiring (which request-scoped session backs the repository) out of the
router and the entrypoint. The production service provider resolves a per-request
``AsyncSession`` via ``get_session`` and binds the SQLAlchemy repository; the
hasher and codec are process-wide singletons.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends

from floresu.accounts.repository import SqlAlchemyAccountRepository
from floresu.accounts.service import AccountService
from floresu.core.db import get_session

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.accounts.passwords import PasswordHasher
    from floresu.accounts.tokens import SessionTokenCodec


def build_account_service_provider(
    hasher: PasswordHasher,
    codec: SessionTokenCodec,
) -> Callable[[AsyncSession], AccountService]:
    """A FastAPI dependency that builds a request-scoped :class:`AccountService`."""

    def provider(session: AsyncSession = Depends(get_session)) -> AccountService:
        return AccountService(SqlAlchemyAccountRepository(session), hasher, codec)

    return provider
