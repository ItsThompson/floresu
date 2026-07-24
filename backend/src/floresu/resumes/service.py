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
upcast to the current schema and validated before it is served. The pure document
surgery, guards, and summaries live in :mod:`floresu.resumes.operations`; this
module orchestrates them and owns persistence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from floresu.core.conflicts import conflict_on_duplicate
from floresu.core.db import transaction
from floresu.core.errors import Conflict, Validation
from floresu.core.events import SCOPE_METADATA_KEY, Action, emit_write_event
from floresu.core.identity import resolve_user_pk
from floresu.core.logging import get_logger
from floresu.core.observability import track_failures
from floresu.resumes.config import CONCURRENT_WRITE_CONFLICT, DEFAULT_LIST_LIMIT, ENTITY_TYPE
from floresu.resumes.cow import (
    EditChannel,
    ResumeEditScope,
    ScopeResolution,
    resolve_edit_scope,
)
from floresu.resumes.creation import (
    JOB_APPLICATION_TAKEN_MESSAGE,
    require_free_job_application,
    seed_document,
    validate_creation_contract,
)
from floresu.resumes.document import (
    LocalItemSourceRefs,
    ResumeDocument,
    referenced_bullet_ids,
    resolve_document,
)
from floresu.resumes.injection import Clock, IdFactory, new_hex_id, utcnow
from floresu.resumes.models import Resume, ResumeKind, ResumeRevision, ResumeStatus
from floresu.resumes.operations import (
    apply_item_order,
    apply_section_order,
    build_item,
    bullet_forked_summary,
    created_summary,
    edited_summary,
    find_item_section,
    find_local_item,
    find_section,
    fork_bullet_reference,
    guard_editable,
    guard_revision,
    item_added_summary,
    item_removed_summary,
    promoted_summary,
    reordered_summary,
    resume_not_found,
    revalidate_document,
    swap_item_to_reference,
)
from floresu.resumes.schemas import (
    AddItemRequest,
    EditedEverywhereResult,
    ForkedThisResumeResult,
    ResumeCreateRequest,
    ResumeReorderRequest,
    ResumeSummary,
    ResumeUpdate,
    ScopeEditRequest,
    ScopeEditResult,
    ScopePromptResult,
    to_record,
    to_summary,
)
from floresu.resumes.upcast import CURRENT_SCHEMA_VERSION, load_document

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.core.actor import Actor
    from floresu.core.events import WriteEventPublisher
    from floresu.library.cow import CanonicalBulletWriter
    from floresu.resumes.repository import ResumeRepository
    from floresu.resumes.resolver import BulletTextResolver
    from floresu.resumes.schemas import ResumeRecord

_log = get_logger("floresu-resumes")


@track_failures("resumes")
class ResumeService:
    """Business rules for the Output layer: resumes, their revisions, and the ref index."""

    def __init__(
        self,
        session: AsyncSession,
        repo: ResumeRepository,
        resolver: BulletTextResolver,
        publisher: WriteEventPublisher,
        bullet_writer: CanonicalBulletWriter,
        *,
        clock: Clock = utcnow,
        id_factory: IdFactory = new_hex_id,
    ) -> None:
        self._session = session
        self._repo = repo
        self._resolver = resolver
        self._publisher = publisher
        self._bullet_writer = bullet_writer
        self._clock = clock
        self._id_factory = id_factory

    async def create(
        self, user_id: str, actor: Actor, request: ResumeCreateRequest
    ) -> ResumeRecord:
        """Create a resume per the contract; snapshot revision 1 and index its refs."""
        pk = resolve_user_pk(user_id)
        validate_creation_contract(request)
        document, title, forked_from = await seed_document(self._repo, pk, request)
        if request.kind is ResumeKind.APPLICATION:
            assert request.job_application_id is not None  # guaranteed by the contract check
            await require_free_job_application(self._repo, pk, request.job_application_id)
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
            async with conflict_on_duplicate(JOB_APPLICATION_TAKEN_MESSAGE):
                await self._repo.add(resume)
            await self._snapshot_and_index(
                pk, resume, document, actor, Action.CREATE, summary=created_summary(resume)
            )
        return to_record(resume, document)

    async def get(self, user_id: str, resume_id: int) -> ResumeRecord:
        """Read one resume; upcast its document to the current schema, then serve."""
        pk = resolve_user_pk(user_id)
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
        pk = resolve_user_pk(user_id)
        rows = await self._repo.list_resumes(
            pk, kind=kind, include_archived=include_archived, limit=limit
        )
        return [to_summary(row) for row in rows]

    async def update(
        self, user_id: str, resume_id: int, actor: Actor, if_match: int, body: ResumeUpdate
    ) -> ResumeRecord:
        """Overwrite the authoritative document (If-Match guarded); snapshot and reindex."""
        pk = resolve_user_pk(user_id)
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
                pk, resume, document, actor, Action.UPDATE, summary=edited_summary(resume)
            )
        return to_record(resume, document)

    async def add_item(
        self, user_id: str, resume_id: int, actor: Actor, if_match: int, request: AddItemRequest
    ) -> ResumeRecord:
        """Append one item to a section (server-minted id); snapshot and reindex."""
        pk = resolve_user_pk(user_id)
        resume = await self._prepare_write(pk, resume_id, if_match)
        document = load_document(resume.document)
        section = find_section(document, request.section_id)
        item = build_item(request.item, self._id_factory())
        section.items[item.id] = item
        section.item_order.append(item.id)
        document = revalidate_document(document)
        async with transaction(self._session):
            await self._apply_save(
                pk, resume, document, actor, Action.UPDATE, summary=item_added_summary(resume)
            )
        return to_record(resume, document)

    async def remove_item(
        self, user_id: str, resume_id: int, actor: Actor, if_match: int, item_id: str
    ) -> ResumeRecord:
        """Remove one item from its section; snapshot and reindex."""
        pk = resolve_user_pk(user_id)
        resume = await self._prepare_write(pk, resume_id, if_match)
        document = load_document(resume.document)
        section = find_item_section(document, item_id)
        del section.items[item_id]
        section.item_order.remove(item_id)
        document = revalidate_document(document)
        async with transaction(self._session):
            await self._apply_save(
                pk, resume, document, actor, Action.UPDATE, summary=item_removed_summary(resume)
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
        pk = resolve_user_pk(user_id)
        resume = await self._prepare_write(pk, resume_id, if_match)
        document = load_document(resume.document)
        if request.section_order is not None:
            apply_section_order(document, request.section_order)
        if request.item_orders is not None:
            for section_id, order in request.item_orders.items():
                apply_item_order(find_section(document, section_id), order)
        document = revalidate_document(document)
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
                summary=reordered_summary(resume),
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
        resolve_user_pk(user_id)
        return await self._repo.used_in_count(bullet_id)

    async def bullet_update(
        self, user_id: str, actor: Actor, channel: EditChannel, request: ScopeEditRequest
    ) -> ScopeEditResult:
        """Edit a canonical bullet a resume item resolves to, resolving copy-on-write scope.

        The scope is intent-driven: an agent (MCP) edit carries an explicit scope; a
        web edit prompts only when the bullet is shared (used in two or more
        resumes) and otherwise applies everywhere. ``everywhere`` edits the canonical
        bullet in place (guarded by the bullet ``revision``, re-embedded, every
        reference updates); ``this_resume`` forks a resume-local copy (guarded by the
        resume ``revision``, canonical bullet untouched).
        """
        pk = resolve_user_pk(user_id)
        used_in = await self._repo.used_in_count(request.bullet_id)
        resolution = resolve_edit_scope(
            channel=channel, requested=request.scope, used_in_count=used_in
        )
        if resolution is ScopeResolution.PROMPT:
            return ScopePromptResult(bullet_id=request.bullet_id, used_in_count=used_in)
        if resolution is ScopeResolution.EVERYWHERE:
            return await self._edit_everywhere(pk, actor, request, used_in)
        return await self._fork_this_resume(pk, actor, request)

    async def promote(
        self, user_id: str, resume_id: int, actor: Actor, if_match: int, item_id: str
    ) -> ResumeRecord:
        """Promote a resume-local item into a canonical, searchable library bullet.

        Creates a canonical bullet from the local item's text and provenance
        (enqueuing embedding so it enters the corpus), swaps the item to reference
        the new bullet, reindexes ``resume_bullet_ref``, snapshots the resume, and
        records a ``promote``. The bullet create and the resume write commit in one
        transaction, so a promoted item can never point at an uncommitted bullet.
        """
        pk = resolve_user_pk(user_id)
        resume = await self._prepare_write(pk, resume_id, if_match)
        document = load_document(resume.document)
        local = find_local_item(document, item_id)
        refs = local.source_refs or LocalItemSourceRefs()
        async with transaction(self._session):
            bullet_id = await self._bullet_writer.create_from_local(
                pk,
                actor,
                text=local.text,
                source_ids=list(refs.source_ids),
                worklog_ids=list(refs.worklog_ids),
            )
            swap_item_to_reference(document, item_id, bullet_id)
            document = revalidate_document(document)
            await self._apply_save(
                pk,
                resume,
                document,
                actor,
                Action.PROMOTE,
                summary=promoted_summary(resume),
                metadata={"bullet_id": bullet_id, "item_id": item_id},
            )
        return to_record(resume, document)

    async def _edit_everywhere(
        self, pk: int, actor: Actor, request: ScopeEditRequest, used_in: int
    ) -> EditedEverywhereResult:
        """Apply an ``everywhere`` edit: overwrite the canonical bullet, guarded by its revision."""
        if request.if_match_bullet_revision is None:
            raise Validation(
                "An 'everywhere' edit must carry the bullet revision to guard against a "
                "stale edit.",
                fields={"if_match_bullet_revision": "required for scope=everywhere"},
            )
        async with transaction(self._session):
            record = await self._bullet_writer.edit_text_everywhere(
                pk,
                actor,
                request.bullet_id,
                new_text=request.new_text,
                if_match_revision=request.if_match_bullet_revision,
            )
        return EditedEverywhereResult(bullet=record.model_copy(update={"used_in_count": used_in}))

    async def _fork_this_resume(
        self, pk: int, actor: Actor, request: ScopeEditRequest
    ) -> ForkedThisResumeResult:
        """Apply a ``this_resume`` edit: fork a resume-local copy, guarded by the resume."""
        if request.resume_id is None:
            raise Validation(
                "A 'this_resume' edit must name the resume to fork in.",
                fields={"resume_id": "required for scope=this_resume"},
            )
        if request.if_match_resume_revision is None:
            raise Validation(
                "A 'this_resume' edit must carry the resume revision to guard against a "
                "stale edit.",
                fields={"if_match_resume_revision": "required for scope=this_resume"},
            )
        resume = await self._prepare_write(pk, request.resume_id, request.if_match_resume_revision)
        document = load_document(resume.document)
        fork_bullet_reference(document, request.bullet_id, request.new_text)
        document = revalidate_document(document)
        async with transaction(self._session):
            await self._apply_save(
                pk,
                resume,
                document,
                actor,
                Action.UPDATE,
                summary=bullet_forked_summary(resume),
                metadata={SCOPE_METADATA_KEY: ResumeEditScope.THIS_RESUME.value},
            )
        return ForkedThisResumeResult(resume=to_record(resume, document))

    async def _prepare_write(self, pk: int, resume_id: int, if_match: int) -> Resume:
        """Load the resume and enforce the write preconditions (editable + fresh revision)."""
        resume = await self._load(pk, resume_id)
        guard_editable(resume)
        try:
            guard_revision(resume, if_match)
        except Conflict:
            _log.warning(
                "resume_stale_write",
                resume_id=resume_id,
                if_match=if_match,
                current=resume.revision,
            )
            raise
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
        # Capture the ids before the write: a duplicate-key collision fails the flush
        # and expires the ORM attributes, so reading them in the except would trigger
        # a reload on the rolled-back session instead of logging the conflict.
        resume_id = resume.id
        revision = resume.revision
        await self._repo.set_bullet_refs(resume_id, sorted(ref_ids))
        try:
            async with conflict_on_duplicate(CONCURRENT_WRITE_CONFLICT):
                await self._repo.add_revision(
                    ResumeRevision(
                        resume_id=resume_id,
                        revision_no=revision,
                        document=resolved.model_dump(mode="json"),
                        schema_version=CURRENT_SCHEMA_VERSION,
                    )
                )
        except Conflict:
            _log.warning("resume_write_conflict", resume_id=resume_id, revision=revision)
            raise
        await self._publish(
            pk,
            actor,
            resume.id,
            action,
            summary=summary,
            metadata={**(metadata or {}), "revision": resume.revision},
        )

    async def _load(self, pk: int, resume_id: int) -> Resume:
        resume = await self._repo.get(pk, resume_id)
        if resume is None:
            raise resume_not_found(resume_id)
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
        await emit_write_event(
            self._publisher,
            self._session,
            user_id=user_pk,
            actor=actor,
            entity_type=ENTITY_TYPE,
            entity_id=entity_id,
            action=action,
            summary=summary,
            metadata=metadata,
        )
