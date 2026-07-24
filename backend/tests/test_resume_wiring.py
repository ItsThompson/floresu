"""The resume wiring provider builds a request-scoped service over the seam.

Confirms ``build_resume_service_provider`` reads the write-event publisher off
``app.state.events`` and binds the SQLAlchemy repository and resolver over the
injected session, so the composition root wires the same seam both apps share.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from floresu.resumes.service import ResumeService
from floresu.resumes.wiring import build_resume_service_provider
from tests.support.fakes import CapturingWriteEventPublisher, FakeSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def test_provider_binds_the_session_and_the_app_publisher() -> None:
    publisher = CapturingWriteEventPublisher()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(events=publisher)))
    session = cast("AsyncSession", FakeSession())  # the repo and resolver only store the reference

    provider = build_resume_service_provider()
    service = provider(request, session)

    assert isinstance(service, ResumeService)
    assert service._publisher is publisher
    assert service._session is session
