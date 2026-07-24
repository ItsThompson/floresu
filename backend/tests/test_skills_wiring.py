"""The skills wiring provider builds a request-scoped service over the seam.

Confirms ``build_skill_service_provider`` reads the write-event publisher off
``app.state.events`` and binds the SQLAlchemy repository over the injected session,
so the composition root wires the same seam both apps share.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from floresu.profile.skills.service import SkillService
from floresu.profile.skills.wiring import build_skill_service_provider
from tests.support.fakes import CapturingWriteEventPublisher, FakeSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def test_provider_binds_the_session_and_the_app_publisher() -> None:
    publisher = CapturingWriteEventPublisher()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(events=publisher)))
    session = cast("AsyncSession", FakeSession())  # the repository only stores the reference

    provider = build_skill_service_provider()
    service = provider(request, session)

    assert isinstance(service, SkillService)
    assert service._publisher is publisher
    assert service._session is session
