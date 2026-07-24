"""The jobapps and finalize wiring providers build request-scoped services over the seam.

Confirms ``build_jobapps_service_provider`` and ``build_resume_finalize_service_provider``
read the write-event publisher off ``app.state.events`` and bind the request session, the
injected render module, and the injected object store into their services (the jobapps
provider also builds the finalizer the submit trigger delegates to).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from floresu.jobapps.service import JobApplicationService
from floresu.jobapps.wiring import build_jobapps_service_provider
from floresu.rendering.module import RenderModule
from floresu.resumes.finalize import ResumeFinalizeService
from floresu.resumes.finalize_wiring import build_resume_finalize_service_provider
from tests.rendering_fakes import FakeTypstCompiler
from tests.storage_fakes import FakeObjectStore
from tests.support.fakes import CapturingWriteEventPublisher, FakeSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _request(publisher: CapturingWriteEventPublisher) -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(events=publisher)))


def test_jobapps_provider_builds_a_service_with_a_finalizer() -> None:
    publisher = CapturingWriteEventPublisher()
    session = cast("AsyncSession", FakeSession())
    module = RenderModule(FakeTypstCompiler(), templates_dir=Path("/tmpl"))
    store = FakeObjectStore()

    provider = build_jobapps_service_provider(module, store)
    service = provider(_request(publisher), session=session)

    assert isinstance(service, JobApplicationService)
    # The provider consumed the events seam and bound the request session.
    assert service._publisher is publisher
    assert service._session is session
    # It also built the finalizer the submit trigger delegates to, threading the
    # same session and publisher and the injected render module and object store
    # into it.
    assert isinstance(service._finalizer, ResumeFinalizeService)
    assert service._finalizer._session is session
    assert service._finalizer._publisher is publisher
    assert service._finalizer._render is module
    assert service._finalizer._store is store


def test_finalize_provider_builds_a_service() -> None:
    publisher = CapturingWriteEventPublisher()
    session = cast("AsyncSession", FakeSession())
    module = RenderModule(FakeTypstCompiler(), templates_dir=Path("/tmpl"))
    store = FakeObjectStore()

    provider = build_resume_finalize_service_provider(module, store)
    service = provider(_request(publisher), session=session)

    assert isinstance(service, ResumeFinalizeService)
    # Each injected dependency the finalize service stores is bound by identity.
    assert service._publisher is publisher
    assert service._session is session
    assert service._render is module
    assert service._store is store
