"""The resume render wiring provider builds a request-scoped service over the seam.

Confirms ``build_resume_render_service_provider`` reads the write-event publisher off
``app.state.events`` and binds the request session, the injected render module, and
the injected object store into a :class:`ResumeRenderService`.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from floresu.rendering.module import RenderModule
from floresu.resumes.render_service import ResumeRenderService
from floresu.resumes.render_wiring import build_resume_render_service_provider
from tests.rendering_fakes import FakeTypstCompiler
from tests.storage_fakes import FakeObjectStore
from tests.support.fakes import CapturingWriteEventPublisher, FakeSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def test_provider_binds_the_session_render_module_store_and_publisher() -> None:
    publisher = CapturingWriteEventPublisher()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(events=publisher)))
    session = cast("AsyncSession", FakeSession())  # resolvers only store the reference
    module = RenderModule(FakeTypstCompiler(), templates_dir=Path("/tmpl"))
    store = FakeObjectStore()

    provider = build_resume_render_service_provider(module, store)
    service = provider(request, session)

    assert isinstance(service, ResumeRenderService)
    # Each injected dependency the service stores is bound by identity: a provider
    # that dropped any of them (or ignored app.state.events) would fail here.
    assert service._publisher is publisher
    assert service._session is session
    assert service._render is module
    assert service._store is store
