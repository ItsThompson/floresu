"""Resume creation: the contract check, content seeding, and the 1:1 link guard.

Creation is a distinct concern from mutation: it builds the initial in-memory
:class:`ResumeDocument` for a new resume from the explicit contract, and validates
the job-application link, before the service performs the single INSERT. These are
pure construction and read-only checks (no write), so the service stays the only
writer. ``kind`` chooses the result (living vs application) and is never inferred
from ``source``; a ``from_resume`` / ``duplicate`` create copies the source
document verbatim (references stay references, inline text stays inline) so any
owned source resume is a valid seed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.core.errors import Conflict, Validation
from floresu.resumes.config import DEFAULT_TEMPLATE_ID, DEFAULT_TITLE
from floresu.resumes.document import ResumeDocument
from floresu.resumes.models import ResumeKind
from floresu.resumes.schemas import BlankSource, FromResumeSource, ResumeCreateRequest
from floresu.resumes.upcast import CURRENT_SCHEMA_VERSION, load_document

if TYPE_CHECKING:
    from floresu.resumes.repository import ResumeRepository


def validate_creation_contract(request: ResumeCreateRequest) -> None:
    """Enforce the job-application rule: required for application, forbidden for living."""
    if request.kind is ResumeKind.APPLICATION and request.job_application_id is None:
        raise Validation(
            "An application resume requires a job application.",
            fields={"job_application_id": "Required when kind is application."},
        )
    if request.kind is ResumeKind.LIVING and request.job_application_id is not None:
        raise Validation(
            "A living resume cannot link to a job application.",
            fields={"job_application_id": "Forbidden when kind is living."},
        )


async def seed_document(
    repo: ResumeRepository, pk: int, request: ResumeCreateRequest
) -> tuple[ResumeDocument, str, int | None]:
    """Build the initial document, title, and fork provenance for a create.

    A blank create yields an empty document. A ``from_resume`` / ``duplicate``
    create copies the (upcast-on-read) source document verbatim and records the
    source id as ``forked_from_resume_id``.
    """
    source = request.source
    if isinstance(source, BlankSource):
        template_id = request.template_id or DEFAULT_TEMPLATE_ID
        document = ResumeDocument(schema_version=CURRENT_SCHEMA_VERSION, template_id=template_id)
        return document, request.title or DEFAULT_TITLE, None
    source_id = (
        source.from_resume_id if isinstance(source, FromResumeSource) else source.duplicate_id
    )
    src = await repo.get(pk, source_id)
    if src is None:
        raise Validation(
            "The source resume does not exist or is not yours.",
            fields={"source": f"Unknown resume id {source_id}."},
        )
    source_doc = load_document(src.document)
    document = ResumeDocument(
        schema_version=CURRENT_SCHEMA_VERSION,
        header=source_doc.header.model_copy(deep=True),
        template_id=request.template_id or source_doc.template_id,
        sections=[section.model_copy(deep=True) for section in source_doc.sections],
    )
    return document, request.title or src.title, source_id


async def require_free_job_application(
    repo: ResumeRepository, pk: int, job_application_id: int
) -> None:
    """The application's job application must be owned and not already linked (1:1)."""
    owned = await repo.owned_job_application_ids(pk, [job_application_id])
    if job_application_id not in owned:
        raise Validation(
            "The job application does not exist or is not yours.",
            fields={"job_application_id": f"Unknown id {job_application_id}."},
        )
    if await repo.job_application_link_exists(job_application_id):
        raise Conflict("This job application already has an application resume.")
