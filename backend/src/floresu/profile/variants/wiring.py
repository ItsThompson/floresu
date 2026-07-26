"""Compose the identity-variant dependency graph for both apps.

Declares how a request-scoped :class:`IdentityVariantService` is built and defers
the wiring mechanics (resolving the session, reading the write-event seam) to
:func:`publishing_provider`, so every write publishes through the one seam both
apps share.

This is also where the ``variants -> resumes`` boundary is bridged without a cycle:
the variants domain declares the
:class:`~floresu.profile.variants.repointing.ResumeVariantRepointer` port and never
imports a resumes model, while this composition module binds the resume service
(which owns the resume document, revision, and snapshot rules and structurally
satisfies the port) as the re-pointer the archive flow drives.
"""

from __future__ import annotations

from floresu.core.providers import ServiceProvider, publishing_provider
from floresu.profile.variants.repository import SqlAlchemyIdentityVariantRepository
from floresu.profile.variants.service import IdentityVariantService
from floresu.resumes.wiring import build_resume_service


def build_variant_service_provider() -> ServiceProvider[IdentityVariantService]:
    """A FastAPI dependency that builds a request-scoped :class:`IdentityVariantService`."""
    # The resume service owns the resume document/revision/snapshot rules and
    # structurally satisfies ResumeVariantRepointer, so it is the re-pointer the
    # archive-with-replacement flow drives over the one session and shared seam.
    return publishing_provider(
        lambda session, publisher: IdentityVariantService(
            session,
            SqlAlchemyIdentityVariantRepository(session),
            publisher,
            build_resume_service(session, publisher),
        )
    )
