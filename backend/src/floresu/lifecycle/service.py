"""LifecycleService: the single home for the web-only destructive/recovery rules.

Every permanent delete, the data export, and account deletion run here and
nowhere else, so the router stays thin and the destructive rules exist once. Each
delete wraps its work in the ``transaction`` boundary and publishes exactly one
``DELETE`` :class:`WriteEvent` from inside it, so the audit row (the recovery net)
commits atomically with the hard delete and survives the deleted item (the audit
log has no FK to it). A permanent delete of an embeddable item also purges its
polymorphic ``embeddings`` row in the same transaction, because that row has no FK
to the item and so does not cascade.

Deleting a resume removes the resume row (cascading its revisions and bullet-ref
index) but never touches the rendered PDF in object storage or the finalize audit
row, both retained per the retention rules. Account deletion removes the ``users``
row (cascading every ``user_id``-owned table, ``embeddings`` included) and clears
the OAuth grant chain and session blacklist, which carry the user id without a FK;
it is not audited, because the audit rows cascade away with the account and there
is no channel left to notify. Every destructive method is confirmation-gated at
the contract level.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from floresu.core.db import transaction
from floresu.core.errors import NotFound, Unauthorized, Validation
from floresu.core.events import Action, emit_write_event
from floresu.core.identity import resolve_user_pk
from floresu.core.logging import get_logger
from floresu.core.observability import track_failures
from floresu.embedding.config import EmbedItemKind
from floresu.lifecycle.config import (
    BULLET_ENTITY_TYPE,
    RESUME_ENTITY_TYPE,
    SOURCE_ENTITY_TYPE,
    WORKLOG_ENTITY_TYPE,
)
from floresu.lifecycle.export import ExportInput, build_archive
from floresu.lifecycle.injection import Clock, utcnow
from floresu.lifecycle.schemas import AccountDeletionReceipt, DeletionReceipt

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.core.actor import Actor
    from floresu.core.events import WriteEventPublisher
    from floresu.embedding.repository import EmbeddingRepository
    from floresu.lifecycle.export_repository import ExportRepository
    from floresu.lifecycle.repository import LifecycleRepository

_log = get_logger("floresu-lifecycle")

_CONFIRMATION_REQUIRED = (
    "This action is permanent and cannot be undone; resend with confirm=true to proceed."
)
# A session that resolves to an account no longer present (deleted mid-session) is
# a stale session, not a 404 on a resource.
_STALE_SESSION = "Session expired or revoked; log in again."


@track_failures("lifecycle")
class LifecycleService:
    """Web-human-only permanent delete, data export, and account deletion."""

    def __init__(
        self,
        session: AsyncSession,
        repo: LifecycleRepository,
        export_repo: ExportRepository,
        embeddings: EmbeddingRepository,
        publisher: WriteEventPublisher,
        *,
        clock: Clock = utcnow,
    ) -> None:
        self._session = session
        self._repo = repo
        self._export_repo = export_repo
        self._embeddings = embeddings
        self._publisher = publisher
        self._clock = clock

    async def permanently_delete_worklog(
        self, user_id: str, worklog_id: int, actor: Actor, *, confirm: bool
    ) -> DeletionReceipt:
        """Hard-delete a worklog entry (cascading its edges) and purge its vector."""
        pk = resolve_user_pk(user_id)
        _require_confirmation(confirm)
        async with transaction(self._session):
            title = await self._repo.delete_worklog(pk, worklog_id)
            if title is None:
                raise _not_found("worklog entry", worklog_id)
            await self._embeddings.delete(EmbedItemKind.WORKLOG, worklog_id)
            await self._publish(
                pk, actor, WORKLOG_ENTITY_TYPE, worklog_id, f"Permanently deleted worklog “{title}”"
            )
        return _receipt(WORKLOG_ENTITY_TYPE, worklog_id, embedding_purged=True)

    async def permanently_delete_source(
        self, user_id: str, source_id: int, actor: Actor, *, confirm: bool
    ) -> DeletionReceipt:
        """Hard-delete a source (cascading its subtype and join rows) and purge its vector."""
        pk = resolve_user_pk(user_id)
        _require_confirmation(confirm)
        async with transaction(self._session):
            found = await self._repo.delete_source(pk, source_id)
            if found is None:
                raise _not_found("source", source_id)
            kind, label = found
            await self._embeddings.delete(EmbedItemKind.SOURCE, source_id)
            await self._publish(
                pk, actor, SOURCE_ENTITY_TYPE, source_id, f"Permanently deleted {kind} “{label}”"
            )
        return _receipt(SOURCE_ENTITY_TYPE, source_id, embedding_purged=True)

    async def permanently_delete_bullet(
        self, user_id: str, bullet_id: int, actor: Actor, *, confirm: bool
    ) -> DeletionReceipt:
        """Hard-delete a bulletpoint (cascading its edges and refs) and purge its vector."""
        pk = resolve_user_pk(user_id)
        _require_confirmation(confirm)
        async with transaction(self._session):
            text = await self._repo.delete_bullet(pk, bullet_id)
            if text is None:
                raise _not_found("bulletpoint", bullet_id)
            await self._embeddings.delete(EmbedItemKind.BULLET, bullet_id)
            await self._publish(
                pk,
                actor,
                BULLET_ENTITY_TYPE,
                bullet_id,
                f"Permanently deleted bulletpoint “{_preview(text)}”",
            )
        return _receipt(BULLET_ENTITY_TYPE, bullet_id, embedding_purged=True)

    async def permanently_delete_resume(
        self, user_id: str, resume_id: int, actor: Actor, *, confirm: bool
    ) -> DeletionReceipt:
        """Hard-delete a resume (cascading its revisions and refs); the PDF and audit stay."""
        pk = resolve_user_pk(user_id)
        _require_confirmation(confirm)
        async with transaction(self._session):
            title = await self._repo.delete_resume(pk, resume_id)
            if title is None:
                raise _not_found("resume", resume_id)
            await self._publish(
                pk, actor, RESUME_ENTITY_TYPE, resume_id, f"Permanently deleted resume “{title}”"
            )
        return _receipt(RESUME_ENTITY_TYPE, resume_id, embedding_purged=False)

    async def export_data(self, user_id: str) -> dict[str, Any]:
        """Assemble the complete export archive of the account's records (read-only)."""
        pk = resolve_user_pk(user_id)
        account = await self._export_repo.account(pk)
        if account is None:
            raise Unauthorized(_STALE_SESSION)
        sources = list(await self._export_repo.sources(pk))
        source_details = await self._export_repo.source_details(pk)
        # A base source with no resolved subtype detail is unreachable in production
        # (the composite FK guarantees one) and is omitted from the archive rather
        # than exported half-formed. Log it so a silent omission is observable.
        missing_detail = [source.id for source in sources if source.id not in source_details]
        if missing_detail:
            _log.warning("export_source_missing_subtype", user_id=pk, source_ids=missing_detail)
        data = ExportInput(
            account=account,
            worklog=list(await self._export_repo.worklog(pk)),
            worklog_tags=await self._export_repo.worklog_tags(pk),
            worklog_sources=await self._export_repo.worklog_sources(pk),
            sources=sources,
            source_details=source_details,
            bullets=list(await self._export_repo.bullets(pk)),
            bullet_sources=await self._export_repo.bullet_sources(pk),
            bullet_worklogs=await self._export_repo.bullet_worklogs(pk),
            skills=list(await self._export_repo.skills(pk)),
            variants=list(await self._export_repo.variants(pk)),
            tags=list(await self._export_repo.tags(pk)),
            resumes=list(await self._export_repo.resumes(pk)),
            job_applications=list(await self._export_repo.job_applications(pk)),
        )
        return build_archive(data, exported_at=self._clock())

    async def delete_account(self, user_id: str, *, confirm: bool) -> AccountDeletionReceipt:
        """Irreversibly remove the account: cascade its records and revoke every agent."""
        pk = resolve_user_pk(user_id)
        _require_confirmation(confirm)
        async with transaction(self._session):
            agent_count = await self._repo.count_active_agents(user_id)
            await self._repo.revoke_agents(user_id)
            await self._repo.clear_session_blacklist(pk)
            deleted = await self._repo.delete_user(pk)
            if not deleted:
                raise Unauthorized(_STALE_SESSION)
        # Not audited: the audit rows cascade away with the account and there is no
        # feed channel left to publish to. Recorded structurally instead.
        _log.info("account_deleted", user_id=pk, revoked_agents=agent_count)
        return AccountDeletionReceipt(deleted=True, revoked_agent_count=agent_count)

    async def _publish(
        self, user_pk: int, actor: Actor, entity_type: str, entity_id: int, summary: str
    ) -> None:
        await emit_write_event(
            self._publisher,
            self._session,
            user_id=user_pk,
            actor=actor,
            entity_type=entity_type,
            entity_id=entity_id,
            action=Action.DELETE,
            summary=summary,
            metadata={"permanent": True},
        )


def _require_confirmation(confirm: bool) -> None:
    if not confirm:
        raise Validation(_CONFIRMATION_REQUIRED, fields={"confirm": _CONFIRMATION_REQUIRED})


def _not_found(label: str, entity_id: int) -> NotFound:
    # 404-over-403: an item another account owns is scoped out, so a miss reads as
    # "does not exist" with no cross-account existence leak.
    return NotFound(f"No {label} with id {entity_id}.")


def _receipt(entity_type: str, entity_id: int, *, embedding_purged: bool) -> DeletionReceipt:
    return DeletionReceipt(
        entity_type=entity_type, entity_id=entity_id, embedding_purged=embedding_purged
    )


_PREVIEW_LIMIT = 60


def _preview(text: str) -> str:
    """A short single-line preview of bullet text for the audit summary line."""
    single_line = " ".join(text.split())
    if len(single_line) <= _PREVIEW_LIMIT:
        return single_line
    return f"{single_line[: _PREVIEW_LIMIT - 1]}…"
