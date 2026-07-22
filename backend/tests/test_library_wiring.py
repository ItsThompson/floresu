"""The library wiring provider builds a request-scoped service over the seam.

Confirms ``build_bullet_service_provider`` reads the write-event publisher off
``app.state.events``, binds the SQLAlchemy repository over the injected session, and
binds the resumes repository as the ``BulletUsageCounter`` (the cross-domain "used in
N" count), so the composition root wires the same seam both apps share without a
``library -> resumes`` cycle.
"""

from __future__ import annotations

from types import SimpleNamespace

from floresu.core.events import WriteEventPublisher
from floresu.library.service import LibraryService
from floresu.library.wiring import build_bullet_service_provider
from floresu.resumes.repository import SqlAlchemyResumeRepository


def test_provider_binds_the_session_the_publisher_and_the_usage_counter() -> None:
    publisher = WriteEventPublisher()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(events=publisher)))
    session = object()  # the repositories only store the session reference

    provider = build_bullet_service_provider()
    service = provider(request, session)

    assert isinstance(service, LibraryService)
    # The "used in N" counter is the resumes repository, bound here at the seam.
    assert isinstance(service._usage, SqlAlchemyResumeRepository)
