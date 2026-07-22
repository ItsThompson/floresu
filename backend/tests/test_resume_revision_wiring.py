"""The resume revision wiring provider constructs the service over the request seam.

Confirms ``build_resume_revision_service_provider`` returns a provider that builds a
:class:`ResumeRevisionService` from the request session and the injected object store.
Reads only: the provider takes no request and needs no write-event publisher.
"""

from __future__ import annotations

from floresu.resumes.revision_service import ResumeRevisionService
from floresu.resumes.revision_wiring import build_resume_revision_service_provider
from tests.storage_fakes import FakeObjectStore


def test_provider_binds_the_session_and_object_store() -> None:
    store = FakeObjectStore()
    session = object()  # the repository only stores the session reference

    provider = build_resume_revision_service_provider(store)
    service = provider(session)

    assert isinstance(service, ResumeRevisionService)
