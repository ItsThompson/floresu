"""Compose the identity-variant dependency graph for both apps.

Declares how a request-scoped :class:`IdentityVariantService` is built and defers
the wiring mechanics (resolving the session, reading the write-event seam) to
:func:`publishing_provider`, so every write publishes through the one seam both
apps share.
"""

from __future__ import annotations

from floresu.core.providers import ServiceProvider, publishing_provider
from floresu.profile.variants.repository import SqlAlchemyIdentityVariantRepository
from floresu.profile.variants.service import IdentityVariantService


def build_variant_service_provider() -> ServiceProvider[IdentityVariantService]:
    """A FastAPI dependency that builds a request-scoped :class:`IdentityVariantService`."""
    return publishing_provider(
        lambda session, publisher: IdentityVariantService(
            session, SqlAlchemyIdentityVariantRepository(session), publisher
        )
    )
