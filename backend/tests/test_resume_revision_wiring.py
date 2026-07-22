"""The resume revision wiring provider builds a request-scoped service over the seam.

Confirms ``build_resume_revision_service_provider`` binds the request session's render
repository and the injected object store into a :class:`ResumeRevisionService`. Reads
only: the provider takes no request and needs no write-event publisher.
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
