"""Compose the skills dependency graph for both apps.

Declares how a request-scoped :class:`SkillService` is built and defers the
wiring mechanics (resolving the session, reading the write-event seam) to
:func:`publishing_provider`, so every write publishes through the one seam both
apps share.
"""

from __future__ import annotations

from floresu.core.providers import ServiceProvider, publishing_provider
from floresu.profile.skills.repository import SqlAlchemySkillRepository
from floresu.profile.skills.service import SkillService


def build_skill_service_provider() -> ServiceProvider[SkillService]:
    """A FastAPI dependency that builds a request-scoped :class:`SkillService`."""
    return publishing_provider(
        lambda session, publisher: SkillService(
            session, SqlAlchemySkillRepository(session), publisher
        )
    )
