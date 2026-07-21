"""IdentityVariantService: variant lifecycle rules, the default invariant, and audit.

Every variant write runs here and nowhere else, so the web and agent adapters stay
thin and provenance is uniform. Each mutate wraps its work in the ``transaction``
boundary and publishes exactly one :class:`WriteEvent` through the write-event seam
from *inside* that boundary, so the audit row (the seam's transactional consumer)
commits or rolls back atomically with the write. The resolved :class:`Actor` is
carried into every event.

The exactly-one-default invariant is enforced here: creating the first variant
sets it as default automatically, and marking a different variant default flips the
previous default off in the same transaction. The default cannot be archived until
another variant is made default. Archiving a variant a living resume references is
blocked and surfaces a structured replacement-required signal (the referencing
resume ids), which the resume-side prompt resolves. Variants are unordered, so
there is no reorder operation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from floresu.core.conflicts import conflict_on_duplicate
from floresu.core.db import transaction
from floresu.core.errors import Conflict, NotFound, Unauthorized, Validation, Violation
from floresu.core.events import Action, WriteEvent
from floresu.core.observability import track_failures
from floresu.profile.injection import Clock, utcnow
from floresu.profile.variants.config import (
    DEFAULT_LIST_LIMIT,
    ENTITY_TYPE,
    REPLACEMENT_REQUIRED_RULE,
)
from floresu.profile.variants.models import IdentityVariant
from floresu.profile.variants.schemas import (
    IdentityVariantRead,
    contact_to_storage,
    links_to_storage,
    to_read,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.core.actor import Actor
    from floresu.core.events import WriteEventPublisher
    from floresu.profile.variants.repository import IdentityVariantRepository
    from floresu.profile.variants.schemas import IdentityVariantWrite


@track_failures("identity_variants")
class IdentityVariantService:
    """Business rules for identity variants and the exactly-one-default invariant."""

    def __init__(
        self,
        session: AsyncSession,
        repo: IdentityVariantRepository,
        publisher: WriteEventPublisher,
        *,
        clock: Clock = utcnow,
    ) -> None:
        self._session = session
        self._repo = repo
        self._publisher = publisher
        self._clock = clock

    async def create(
        self, user_id: str, actor: Actor, write: IdentityVariantWrite
    ) -> IdentityVariantRead:
        """Create a variant; the first variant (no active default yet) becomes default."""
        pk = _require_user_pk(user_id)
        existing_default = await self._repo.current_default(pk)
        # The first variant is forced default so the invariant holds from the start;
        # a later variant becomes default only if the write asks for it.
        make_default = write.is_default or existing_default is None
        variant = IdentityVariant(
            user_id=pk,
            label=write.label,
            full_name=write.full_name,
            contact=contact_to_storage(write.contact),
            links=links_to_storage(write.links),
            is_default=make_default,
        )
        async with (
            conflict_on_duplicate(_duplicate_message(write.label)),
            transaction(self._session),
        ):
            await self._repo.add(variant)
            if make_default and existing_default is not None:
                existing_default.is_default = False
            # Carry the default marker whenever this create makes the variant the
            # default (the forced first variant, or an explicit is_default), so the
            # create and update promotion paths publish a symmetric signal.
            await self._publish(
                pk,
                actor,
                variant.id,
                Action.CREATE,
                _created_summary(variant),
                metadata={"is_default": True} if make_default else None,
            )
        return to_read(variant)

    async def get(self, user_id: str, variant_id: int) -> IdentityVariantRead:
        """Read one variant."""
        pk = _require_user_pk(user_id)
        return to_read(await self._require(pk, variant_id))

    async def list_variants(
        self, user_id: str, *, include_archived: bool = False, limit: int = DEFAULT_LIST_LIMIT
    ) -> list[IdentityVariantRead]:
        """List variants (by label); active-only by default."""
        pk = _require_user_pk(user_id)
        variants = await self._repo.list(pk, include_archived=include_archived, limit=limit)
        return [to_read(variant) for variant in variants]

    async def update(
        self, user_id: str, variant_id: int, actor: Actor, write: IdentityVariantWrite
    ) -> IdentityVariantRead:
        """Overwrite the fields; promoting to default flips the previous default off.

        The default is set through this update (variants have no reorder). Directly
        unsetting the sole default is rejected: promote another variant instead, so
        exactly one default always exists.
        """
        pk = _require_user_pk(user_id)
        variant = await self._require(pk, variant_id)
        was_default = variant.is_default
        if not write.is_default and was_default:
            raise Conflict(
                "The default variant cannot be unset directly; make another variant the default."
            )
        async with (
            conflict_on_duplicate(_duplicate_message(write.label)),
            transaction(self._session),
        ):
            variant.label = write.label
            variant.full_name = write.full_name
            variant.contact = contact_to_storage(write.contact)
            variant.links = links_to_storage(write.links)
            if write.is_default:
                # Idempotent: promoting the current default flips nothing; promoting
                # another variant flips the old default off in this same transaction.
                await self._promote_to_default(pk, variant)
            promoted = write.is_default and not was_default
            await self._publish(
                pk,
                actor,
                variant.id,
                Action.UPDATE,
                _edited_summary(variant),
                metadata={"is_default": True} if promoted else None,
            )
        return to_read(variant)

    async def archive(self, user_id: str, variant_id: int, actor: Actor) -> IdentityVariantRead:
        """Soft-archive; blocked while default or referenced by a living resume."""
        pk = _require_user_pk(user_id)
        variant = await self._require(pk, variant_id)
        if variant.archived_at is not None:
            raise Conflict("This variant is already archived.")
        if variant.is_default:
            raise Conflict(
                "The default variant cannot be archived; make another variant the default first."
            )
        referencing = await self._repo.resume_ids_referencing(pk, variant_id)
        if referencing:
            raise _replacement_required(variant, referencing)
        async with transaction(self._session):
            variant.archived_at = self._clock()
            await self._publish(pk, actor, variant.id, Action.ARCHIVE, _archived_summary(variant))
        return to_read(variant)

    async def restore(self, user_id: str, variant_id: int, actor: Actor) -> IdentityVariantRead:
        """Clear ``archived_at``; a restored variant is not default until promoted."""
        pk = _require_user_pk(user_id)
        variant = await self._require(pk, variant_id)
        if variant.archived_at is None:
            raise Conflict("This variant is not archived.")
        async with transaction(self._session):
            variant.archived_at = None
            await self._publish(pk, actor, variant.id, Action.RESTORE, _restored_summary(variant))
        return to_read(variant)

    async def _promote_to_default(self, user_pk: int, variant: IdentityVariant) -> None:
        """Flip the current active default off and set this variant default (same txn)."""
        current = await self._repo.current_default(user_pk)
        if current is not None and current.id != variant.id:
            current.is_default = False
        variant.is_default = True

    async def _require(self, user_pk: int, variant_id: int) -> IdentityVariant:
        variant = await self._repo.get(user_pk, variant_id)
        if variant is None:
            raise _not_found(variant_id)
        return variant

    async def _publish(
        self,
        user_pk: int,
        actor: Actor,
        entity_id: int,
        action: Action,
        summary: str,
        *,
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


def _require_user_pk(user_id: str) -> int:
    """Cast the resolved string identity to the bigint PK, or reject as stale."""
    try:
        return int(user_id)
    except ValueError as exc:
        raise Unauthorized("Session is invalid or expired.") from exc


def _not_found(variant_id: int) -> NotFound:
    # 404-over-403: a variant another account owns is scoped out of the read, so a
    # miss is indistinguishable from "does not exist" (no existence leak).
    return NotFound(f"No identity variant with id {variant_id}.")


def _replacement_required(variant: IdentityVariant, resume_ids: Sequence[int]) -> Validation:
    """The structured replacement-required signal for a referenced-variant archive."""
    return Validation(
        "This variant is used by a living resume; choose a replacement before archiving.",
        violations=[
            Violation(
                rule=REPLACEMENT_REQUIRED_RULE,
                ids=[str(resume_id) for resume_id in resume_ids],
                message=f"“{variant.label}” is referenced by {len(resume_ids)} living resume(s).",
            )
        ],
    )


def _duplicate_message(label: str) -> str:
    return f"A variant labeled “{label}” already exists."


def _created_summary(variant: IdentityVariant) -> str:
    return f"Added identity variant “{variant.label}”"


def _edited_summary(variant: IdentityVariant) -> str:
    return f"Edited identity variant “{variant.label}”"


def _archived_summary(variant: IdentityVariant) -> str:
    return f"Archived identity variant “{variant.label}”"


def _restored_summary(variant: IdentityVariant) -> str:
    return f"Restored identity variant “{variant.label}”"
