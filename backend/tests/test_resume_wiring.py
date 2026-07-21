"""The resume wiring provider builds a request-scoped service over the seam.

Confirms ``build_resume_service_provider`` reads the write-event publisher off
``app.state.events`` and binds the SQLAlchemy repository and resolver over the
injected session, so the composition root wires the same seam both apps share.
"""

from __future__ import annotations

from types import SimpleNamespace

from floresu.core.events import WriteEventPublisher
from floresu.resumes.service import ResumeService
from floresu.resumes.wiring import build_resume_service_provider


def test_provider_binds_the_session_and_the_app_publisher() -> None:
    publisher = WriteEventPublisher()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(events=publisher)))
    session = object()  # the repository and resolver only store the session reference

    provider = build_resume_service_provider()
    service = provider(request, session)

    assert isinstance(service, ResumeService)
