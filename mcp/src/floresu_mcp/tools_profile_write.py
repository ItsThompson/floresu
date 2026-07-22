"""Profile write tools: the one ``profile_*`` write family, parameterized by kind.

Mirrors the read family. The four ground-truth source kinds hit ``/sources``
(carrying the ``kind`` discriminator the backend union expects); skill and
identity_variant hit their own endpoints (their write bodies carry no kind, so it
is dropped). :func:`_dispatch_create` / :func:`_dispatch_update` /
:func:`_dispatch_archive` are the one place that knows this split; each tool stays
a thin adapter (resolve identity from the bearer, check the rate limit, make
exactly one internal call, validate the response into the kind's shape).

Source content triggers embedding, so ``profile_create`` / ``profile_update`` for
a source kind count against the tighter embed-write budget; skill and variant
writes do not. Reorder is valid for sources and skills but not identity variants
(unordered; the default is set via ``profile_update``), so a variant reorder is a
validation error before any internal call.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import TypeAdapter

from floresu_mcp.config import SCOPE_FULL
from floresu_mcp.schemas_profile import ProfileKind, ProfileRecord, ProfileSummary, SourceKind
from floresu_mcp.schemas_profile_write import ProfileWriteInput
from floresu_mcp.scopes import AgentContext, require_scope
from floresu_mcp.tool_errors import raise_for_problem
from floresu_mcp.tool_registry import counted_tool_registrar

if TYPE_CHECKING:
    import httpx
    from mcp.server.fastmcp import FastMCP

    from floresu_mcp.client import InternalApiClient
    from floresu_mcp.ratelimit import RateLimiter

# The four ground-truth source kinds share the /sources endpoint; skill and
# identity_variant have their own. Source content is embedded, so a source write
# counts against the embed-write budget.
_SOURCE_KINDS: frozenset[ProfileKind] = frozenset(
    {ProfileKind.ROLE, ProfileKind.PROJECT, ProfileKind.CERTIFICATION, ProfileKind.EDUCATION}
)

_PROFILE_RECORD: TypeAdapter[ProfileRecord] = TypeAdapter(ProfileRecord)
_PROFILE_SUMMARIES: TypeAdapter[list[ProfileSummary]] = TypeAdapter(list[ProfileSummary])

_PROFILE_CREATE = ToolAnnotations(
    title="Create a profile item",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)
_PROFILE_UPDATE = ToolAnnotations(
    title="Update a profile item",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
_PROFILE_ARCHIVE = ToolAnnotations(
    title="Archive a profile item",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
_PROFILE_REORDER = ToolAnnotations(
    title="Reorder profile items of a kind",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def _is_source(kind: ProfileKind) -> bool:
    """Whether the kind is one of the four ground-truth source kinds."""
    return kind in _SOURCE_KINDS


async def _dispatch_create(
    client: InternalApiClient, item: ProfileWriteInput, user_id: str, actor: str
) -> httpx.Response:
    """The one internal create call for the item's kind."""
    if _is_source(item.kind):
        return await client.source_create(user_id, actor, item.model_dump(mode="json"))
    if item.kind is ProfileKind.SKILL:
        return await client.skill_create(
            user_id, actor, item.model_dump(mode="json", exclude={"kind"})
        )
    return await client.variant_create(
        user_id, actor, item.model_dump(mode="json", exclude={"kind"})
    )


async def _dispatch_update(
    client: InternalApiClient, item: ProfileWriteInput, item_id: int, user_id: str, actor: str
) -> httpx.Response:
    """The one internal update call for the item's kind."""
    if _is_source(item.kind):
        return await client.source_update(user_id, actor, item_id, item.model_dump(mode="json"))
    if item.kind is ProfileKind.SKILL:
        return await client.skill_update(
            user_id, actor, item_id, item.model_dump(mode="json", exclude={"kind"})
        )
    return await client.variant_update(
        user_id, actor, item_id, item.model_dump(mode="json", exclude={"kind"})
    )


async def _dispatch_archive(
    client: InternalApiClient, kind: ProfileKind, item_id: int, user_id: str, actor: str
) -> httpx.Response:
    """The one internal archive call for the requested kind."""
    if _is_source(kind):
        return await client.source_archive(user_id, actor, item_id)
    if kind is ProfileKind.SKILL:
        return await client.skill_archive(user_id, actor, item_id)
    return await client.variant_archive(user_id, actor, item_id)


async def _dispatch_reorder(
    client: InternalApiClient, kind: ProfileKind, ordered_ids: list[int], user_id: str, actor: str
) -> httpx.Response:
    """The one internal reorder call; a variant reorder is rejected up front."""
    if _is_source(kind):
        source_kind = SourceKind(kind.value)
        return await client.sources_reorder(
            user_id, actor, {"kind": source_kind.value, "source_ids": ordered_ids}
        )
    if kind is ProfileKind.SKILL:
        return await client.skills_reorder(user_id, actor, {"skill_ids": ordered_ids})
    raise ToolError(
        "invalid_argument: identity_variant items are unordered and cannot be reordered; "
        "set the default variant with profile_update (is_default) instead."
    )


def register_profile_write_tools(
    mcp: FastMCP, client: InternalApiClient, limiter: RateLimiter
) -> None:
    """Register the parameterized profile write tools onto ``mcp``."""
    tool = counted_tool_registrar(mcp)

    @tool(_PROFILE_CREATE)
    async def profile_create(item: ProfileWriteInput, ctx: AgentContext) -> ProfileRecord:
        """Create a profile item. The kind (role, project, certification, education,
        skill, or identity_variant) is carried in the item body and validates its
        own required fields. Returns the created item."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id, embed_write=_is_source(item.kind))
        response = await _dispatch_create(client, item, user_id, actor)
        return _PROFILE_RECORD.validate_python(raise_for_problem(response).json())

    @tool(_PROFILE_UPDATE)
    async def profile_update(
        item_id: int, item: ProfileWriteInput, ctx: AgentContext
    ) -> ProfileRecord:
        """Overwrite a profile item of the item body's kind (full representation; the
        kind is immutable). Returns the updated item."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id, embed_write=_is_source(item.kind))
        response = await _dispatch_update(client, item, item_id, user_id, actor)
        return _PROFILE_RECORD.validate_python(raise_for_problem(response).json())

    @tool(_PROFILE_ARCHIVE)
    async def profile_archive(kind: ProfileKind, item_id: int, ctx: AgentContext) -> ProfileRecord:
        """Soft-archive a profile item of the given kind. This is reversible from the
        web app; agents cannot permanently delete an item. Returns the archived item."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await _dispatch_archive(client, kind, item_id, user_id, actor)
        return _PROFILE_RECORD.validate_python(raise_for_problem(response).json())

    @tool(_PROFILE_REORDER)
    async def profile_reorder(
        kind: ProfileKind, ordered_ids: list[int], ctx: AgentContext
    ) -> list[ProfileSummary]:
        """Set the sort order of your items of one kind to exactly ``ordered_ids``
        (a full permutation). Valid for role, project, certification, education, and
        skill; not for identity_variant (unordered). Returns the reordered items."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await _dispatch_reorder(client, kind, ordered_ids, user_id, actor)
        return _PROFILE_SUMMARIES.validate_python(raise_for_problem(response).json())
