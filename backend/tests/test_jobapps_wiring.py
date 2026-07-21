"""The jobapps and finalize wiring providers build request-scoped services over the seam.

Confirms ``build_jobapps_service_provider`` and ``build_resume_finalize_service_provider``
read the write-event publisher off ``app.state.events`` and bind the request session, the
injected render module, and the injected object store into their services (the jobapps
provider also builds the finalizer the submit trigger delegates to).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from floresu.core.events import WriteEventPublisher
from floresu.jobapps.service import JobApplicationService
from floresu.jobapps.wiring import build_jobapps_service_provider
from floresu.rendering.module import RenderModule
from floresu.resumes.finalize import ResumeFinalizeService
from floresu.resumes.finalize_wiring import build_resume_finalize_service_provider
from tests.rendering_fakes import FakeTypstCompiler
from tests.storage_fakes import FakeObjectStore


def _request() -> SimpleNamespace:
    publisher = WriteEventPublisher()
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(events=publisher)))


def test_jobapps_provider_builds_a_service_with_a_finalizer() -> None:
    module = RenderModule(FakeTypstCompiler(), templates_dir=Path("/tmpl"))
    store = FakeObjectStore()

    provider = build_jobapps_service_provider(module, store)
    service = provider(_request(), session=object())

    assert isinstance(service, JobApplicationService)


def test_finalize_provider_builds_a_service() -> None:
    module = RenderModule(FakeTypstCompiler(), templates_dir=Path("/tmpl"))
    store = FakeObjectStore()

    provider = build_resume_finalize_service_provider(module, store)
    service = provider(_request(), session=object())

    assert isinstance(service, ResumeFinalizeService)
