"""ResumeService: the single home for resume lifecycle rules and transactions.

Every resume write runs here and nowhere else, so the web and agent adapters stay
thin, the JSONB document is the one authoritative content, and its write-derived
scalar columns (``title``, ``schema_version``, ``revision``) and the
``resume_bullet_ref`` index cannot drift. Each mutate wraps its work in the
``transaction`` boundary and publishes exactly one :class:`WriteEvent` through the
write-event seam from *inside* that boundary, so the audit row commits or rolls
back atomically with the content write. The resolved :class:`Actor` is carried
into every event.

Creation honors the explicit contract: ``kind`` chooses living vs application and
is never inferred from ``source``; a job application is required for an application
resume and forbidden for a living one. Every save runs one invariant pipeline:
guard the optimistic ``revision`` (a stale write is rejected with a recoverable
re-read/retry conflict, never silently overwritten), validate the document against
the current schema, reindex ``resume_bullet_ref`` to exactly the bullets the live
document references, append a keep-all revision snapshot of the *fully resolved*
document (references resolved to text at that moment, so a later library edit never
rewrites the past), and increment ``revision``. On read, an older document is
upcast to the current schema and validated before it is served. Copy-on-write scope
resolution, promote, finalize, and rendering build on this substrate elsewhere.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from floresu.core.db import transaction
from floresu.core.errors import Conflict, NotFound, Unauthorized, Validation
from floresu.core.events import Action, WriteEvent
from floresu.core.observability import track_failures
from floresu.resumes.config import (
    DEFAULT_LIST_LIMIT,
    DEFAULT_TEMPLATE_ID,
    DEFAULT_TITLE,
    ENTITY_TYPE,
)
from floresu.resumes.document import (
    LibraryRefItem,
    LocalItem,
    ResumeDocument,
    ResumeSection,
    referenced_bullet_ids,
    resolve_document,
)
from floresu.resumes.injection import Clock, IdFactory, new_item_id, utcnow
from floresu.resumes.models import Resume, ResumeKind, ResumeRevision, ResumeStatus
from floresu.resumes.schemas import (
    AddItemRequest,
    BlankSource,
    FromResumeSource,
    LibraryRefItemInput,
    ResumeCreateRequest,
    ResumeItemInput,
    ResumeReorderRequest,
    ResumeSummary,
    ResumeUpdate,
    to_record,
    to_summary,
)
from floresu.resumes.upcast import CURRENT_SCHEMA_VERSION, load_document

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.core.actor import Actor
    from floresu.core.events import WriteEventPublisher
    from floresu.resumes.repository import ResumeRepository
    from floresu.resumes.resolver import BulletTextResolver
    from floresu.resumes.schemas import ResumeRecord


@track_failures("resumes")
class ResumeService:
    """Business rules for the Output layer: resumes, their revisions, and the ref index."""

    def __init__(
        self,
        session: AsyncSession,
        repo: ResumeRepository,
        resolver: BulletTextResolver,
        publisher: WriteEventPublisher,
        *,
        clock: Clock = utcnow,
        id_factory: IdFactory = new_item_id,
    ) -> None:
        self._session = session
        self._repo = repo
        self._resolver = resolver
        self._publisher = publisher
        self._clock = clock
        self._id_factory = id_factory

    async def create(
        self, user_id: str, actor: Actor, request: ResumeCreateRequest
    ) -> ResumeRecord:
        """Create a resume per the contract; snapshot revision 1 and index its refs."""
        pk = _require_user_pk(user_id)
        _validate_contract(request)
        document, title, forked_from = await self._seed(pk, request)
        if request.kind is ResumeKind.APPLICATION:
            await self._require_free_job_application(pk, request.job_application_id)
        now = self._clock()
        resume = Resume(
            user_id=pk,
            kind=request.kind,
            status=ResumeStatus.DRAFT,
            title=title,
            schema_version=CURRENT_SCHEMA_VERSION,
            revision=1,
            document=document.model_dump(mode="json"),
            forked_from_resume_id=forked_from,
            job_application_id=request.job_application_id,
            created_at=now,
            updated_at=now,
        )
        async with transaction(self._session):
            await self._repo.add(resume)
            await self._snapshot_and_index(
                pk, resume, document, actor, Action.CREATE, summary=_created_summary(resume)
            )
        return to_record(resume, document)

    async def get(self, user_id: str, resume_id: int) -> ResumeRecord:
        """Read one resume; upcast its document to the current schema, then serve."""
        pk = _require_user_pk(user_id)
        resume = await self._load(pk, resume_id)
        return to_record(resume, load_document(resume.document))

    async def list_resumes(
        self,
        user_id: str,
        *,
        kind: ResumeKind | None = None,
        include_archived: bool = False,
        limit: int = DEFAULT_LIST_LIMIT,
    ) -> list[ResumeSummary]:
        """List resumes newest-first; active-only by default, optionally filtered by kind."""
        pk = _require_user_pk(user_id)
        rows = await self._repo.list_resumes(
            pk, kind=kind, include_archived=include_archived, limit=limit
        )
        return [to_summary(row) for row in rows]

    async def update(
        self, user_id: str, resume_id: int, actor: Actor, if_match: int, body: ResumeUpdate
    ) -> ResumeRecord:
        """Overwrite the authoritative document (If-Match guarded); snapshot and reindex."""
        pk = _require_user_pk(user_id)
        resume = await self._prepare_write(pk, resume_id, if_match)
        document = ResumeDocument(
            schema_version=CURRENT_SCHEMA_VERSION,
            header=body.header,
            template_id=body.template_id,
            sections=body.sections,
        )
        async with transaction(self._session):
            resume.title = body.title
            await self._apply_save(
                pk, resume, document, actor, Action.UPDATE, summary=_edited_summary(resume)
            )
        return to_record(resume, document)

    async def add_item(
        self, user_id: str, resume_id: int, actor: Actor, if_match: int, request: AddItemRequest
    ) -> ResumeRecord:
        """Append one item to a section (server-minted id); snapshot and reindex."""
        pk = _require_user_pk(user_id)
        resume = await self._prepare_write(pk, resume_id, if_match)
        document = load_document(resume.document)
        section = _find_section(document, request.section_id)
        item = _build_item(request.item, self._id_factory())
        section.items[item.id] = item
        section.item_order.append(item.id)
        document = _revalidate(document)
        async with transaction(self._session):
            await self._apply_save(
                pk, resume, document, actor, Action.UPDATE, summary=_item_added_summary(resume)
            )
        return to_record(resume, document)

    async def remove_item(
        self, user_id: str, resume_id: int, actor: Actor, if_match: int, item_id: str
    ) -> ResumeRecord:
        """Remove one item from its section; snapshot and reindex."""
        pk = _require_user_pk(user_id)
        resume = await self._prepare_write(pk, resume_id, if_match)
        document = load_document(resume.document)
        section = _find_item_section(document, item_id)
        del section.items[item_id]
        section.item_order.remove(item_id)
        document = _revalidate(document)
        async with transaction(self._session):
            await self._apply_save(
                pk, resume, document, actor, Action.UPDATE, summary=_item_removed_summary(resume)
            )
        return to_record(resume, document)

    async def reorder(
        self,
        user_id: str,
        resume_id: int,
        actor: Actor,
        if_match: int,
        request: ResumeReorderRequest,
    ) -> ResumeRecord:
        """Reorder sections and/or items by id (never by index); records a reorder action."""
        pk = _require_user_pk(user_id)
        resume = await self._prepare_write(pk, resume_id, if_match)
        document = load_document(resume.document)
        if request.section_order is not None:
            _apply_section_order(document, request.section_order)
        if request.item_orders is not None:
            for section_id, order in request.item_orders.items():
                _apply_item_order(_find_section(document, section_id), order)
        document = _revalidate(document)
        metadata: dict[str, Any] = {}
        if request.section_order is not None:
            metadata["section_order"] = request.section_order
        if request.item_orders is not None:
            metadata["item_orders"] = request.item_orders
        async with transaction(self._session):
            await self._apply_save(
                pk,
                resume,
                document,
                actor,
                Action.REORDER,
                summary=_reordered_summary(resume),
                metadata=metadata,
            )
        return to_record(resume, document)

    async def bullet_used_in_count(self, user_id: str, bullet_id: int) -> int:
        """ "Used in N": how many live resumes reference a canonical bullet.

        A finalized resume holds no ``resume_bullet_ref`` rows (finalize drops them
        and its document has no references), so the count reflects live references
        only. Bullet ownership is established by the caller, which resolves the
        bullet in the user's scope before asking.
        """
        _require_user_pk(user_id)
        return await self._repo.used_in_count(bullet_id)

    async def _prepare_write(self, pk: int, resume_id: int, if_match: int) -> Resume:
        """Load the resume and enforce the write preconditions (editable + fresh revision)."""
        resume = await self._load(pk, resume_id)
        _guard_editable(resume)
        _guard_revision(resume, if_match)
        return resume

    async def _apply_save(
        self,
        pk: int,
        resume: Resume,
        document: ResumeDocument,
        actor: Actor,
        action: Action,
        *,
        summary: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Persist a mutated document row (bumping revision), then snapshot and index it."""
        resume.document = document.model_dump(mode="json")
        resume.schema_version = CURRENT_SCHEMA_VERSION
        resume.revision += 1
        resume.updated_at = self._clock()
        await self._snapshot_and_index(
            pk, resume, document, actor, action, summary=summary, metadata=metadata
        )

    async def _snapshot_and_index(
        self,
        pk: int,
        resume: Resume,
        document: ResumeDocument,
        actor: Actor,
        action: Action,
        *,
        summary: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """The invariant every save shares: resolve refs, index, snapshot, publish.

        Runs inside the caller's ``transaction``. Resolving the referenced bullets
        also validates their ownership (an unowned or unknown id is absent from the
        resolver result and rejected), so the reindex and the fully resolved
        snapshot can never carry a foreign or dangling reference.
        """
        ref_ids = referenced_bullet_ids(document)
        texts = await self._resolver.resolve(pk, ref_ids) if ref_ids else {}
        missing = [bullet_id for bullet_id in ref_ids if bullet_id not in texts]
        if missing:
            raise Validation(
                "This resume references a bulletpoint that does not exist or is not yours.",
                fields={"items": f"Unknown bullet id(s): {missing}."},
            )
        resolved = resolve_document(document, texts)
        await self._repo.set_bullet_refs(resume.id, sorted(ref_ids))
        await self._repo.add_revision(
            ResumeRevision(
                resume_id=resume.id,
                revision_no=resume.revision,
                document=resolved.model_dump(mode="json"),
                schema_version=CURRENT_SCHEMA_VERSION,
            )
        )
        await self._publish(
            pk,
            actor,
            resume.id,
            action,
            summary=summary,
            metadata={**(metadata or {}), "revision": resume.revision},
        )

    async def _seed(
        self, pk: int, request: ResumeCreateRequest
    ) -> tuple[ResumeDocument, str, int | None]:
        """Build the initial document, title, and fork provenance for a create.

        A blank create yields an empty document. A ``from_resume`` / ``duplicate``
        create copies the (upcast-on-read) source document verbatim and records the
        source id as ``forked_from_resume_id``; the result kind is set by ``kind``,
        never by the source, so any owned source resume is a valid seed.
        """
        source = request.source
        if isinstance(source, BlankSource):
            template_id = request.template_id or DEFAULT_TEMPLATE_ID
            document = ResumeDocument(
                schema_version=CURRENT_SCHEMA_VERSION, template_id=template_id
            )
            return document, request.title or DEFAULT_TITLE, None
        source_id = (
            source.from_resume_id if isinstance(source, FromResumeSource) else source.duplicate_id
        )
        src = await self._repo.get(pk, source_id)
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

    async def _require_free_job_application(self, pk: int, job_application_id: int | None) -> None:
        """The application's job application must be owned and not already linked (1:1)."""
        # ``job_application_id`` is guaranteed non-null for an application by the contract.
        assert job_application_id is not None
        owned = await self._repo.owned_job_application_ids(pk, [job_application_id])
        if job_application_id not in owned:
            raise Validation(
                "The job application does not exist or is not yours.",
                fields={"job_application_id": f"Unknown id {job_application_id}."},
            )
        if await self._repo.job_application_link_exists(job_application_id):
            raise Conflict("This job application already has an application resume.")

    async def _load(self, pk: int, resume_id: int) -> Resume:
        resume = await self._repo.get(pk, resume_id)
        if resume is None:
            raise _not_found(resume_id)
        return resume

    async def _publish(
        self,
        user_pk: int,
        actor: Actor,
        entity_id: int,
        action: Action,
        *,
        summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self._publisher.publish(
            self._session,
            WriteEvent(
                user_id=user_pk,
                actor=actor,
                entity_type=ENTITY_TYPE,
                entity_id=entity_id,
                action=action,
                summary=summary,
                metadata=metadata,
            ),
        )


def _validate_contract(request: ResumeCreateRequest) -> None:
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


def _build_item(item_input: ResumeItemInput, item_id: str) -> LibraryRefItem | LocalItem:
    """Project an add-item input onto a document item, stamping the server-minted id."""
    if isinstance(item_input, LibraryRefItemInput):
        return LibraryRefItem(id=item_id, bullet_id=item_input.bullet_id)
    return LocalItem(id=item_id, text=item_input.text, source_refs=item_input.source_refs)


def _find_section(document: ResumeDocument, section_id: str) -> ResumeSection:
    for section in document.sections:
        if section.id == section_id:
            return section
    raise Validation(
        "No section with that id on this resume.",
        fields={"section_id": f"Unknown section id {section_id!r}."},
    )


def _find_item_section(document: ResumeDocument, item_id: str) -> ResumeSection:
    for section in document.sections:
        if item_id in section.items:
            return section
    raise NotFound(f"No item with id {item_id!r} on this resume.")


def _apply_section_order(document: ResumeDocument, order: list[str]) -> None:
    current = {section.id: section for section in document.sections}
    if len(set(order)) != len(order):
        raise Validation("The section order contains duplicate ids.")
    if set(order) != set(current):
        raise Validation(
            "A section reorder must list every section exactly once.",
            fields={"section_order": f"Expected the {len(current)} section id(s)."},
        )
    document.sections = [current[section_id] for section_id in order]


def _apply_item_order(section: ResumeSection, order: list[str]) -> None:
    if len(set(order)) != len(order):
        raise Validation("An item order contains duplicate ids.")
    if set(order) != set(section.items):
        raise Validation(
            "An item reorder must list every item in the section exactly once.",
            fields={"item_order": f"Expected the {len(section.items)} item id(s)."},
        )
    section.item_order = list(order)


def _revalidate(document: ResumeDocument) -> ResumeDocument:
    """Re-run the document validators after an in-place mutation."""
    return ResumeDocument.model_validate(document.model_dump(mode="python"))


def _guard_editable(resume: Resume) -> None:
    """A finalized resume is read-only; the only path is to fork a new draft copy."""
    if resume.status is ResumeStatus.FINALIZED:
        raise Conflict("This resume is finalized and read-only; fork a new draft copy to edit.")


def _guard_revision(resume: Resume, if_match: int) -> None:
    """Reject a stale write with a recoverable re-read/retry conflict."""
    if resume.revision != if_match:
        raise Conflict(
            "This resume changed since you loaded it "
            f"(you sent revision {if_match}, current is {resume.revision}); re-read and retry."
        )


def _require_user_pk(user_id: str) -> int:
    """Cast the resolved string identity to the bigint PK, or reject as stale."""
    try:
        return int(user_id)
    except ValueError as exc:
        raise Unauthorized("Session is invalid or expired.") from exc


def _not_found(resume_id: int) -> NotFound:
    # 404-over-403: a resume another account owns is scoped out of the read, so a
    # miss is indistinguishable from "does not exist" (no existence leak).
    return NotFound(f"No resume with id {resume_id}.")


def _created_summary(resume: Resume) -> str:
    return f"Created {resume.kind.value} resume “{resume.title}”"


def _edited_summary(resume: Resume) -> str:
    return f"Edited resume “{resume.title}”"


def _item_added_summary(resume: Resume) -> str:
    return f"Added an item to resume “{resume.title}”"


def _item_removed_summary(resume: Resume) -> str:
    return f"Removed an item from resume “{resume.title}”"


def _reordered_summary(resume: Resume) -> str:
    return f"Reordered resume “{resume.title}”"
