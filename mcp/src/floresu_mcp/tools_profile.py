"""Profile read tools: the one ``profile_*`` family, parameterized by kind.

The family spans three backend endpoints: the four ground-truth source kinds
(``/sources``), skills (``/skills``), and identity variants
(``/identity-variants``). :func:`_dispatch_list` / :func:`_dispatch_get` are the
one place that knows this split; each tool stays a thin adapter (resolve
``(user_id, actor)`` from the bearer, check the rate limit, make exactly one
internal call, validate the response into the kind's read shape). The output type
is a union whose members carry disjoint required fields, so validation resolves
the concrete shape from the backend projection. Both tools are ``readOnlyHint``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import ToolAnnotations
from pydantic import TypeAdapter

from floresu_mcp.config import SCOPE_FULL
from floresu_mcp.schemas_profile import ProfileKind, ProfileRecord, ProfileSummary, SourceKind
from floresu_mcp.scopes import AgentContext, require_scope
from floresu_mcp.tool_errors import raise_for_problem
from floresu_mcp.tool_registry import counted_tool_registrar

if TYPE_CHECKING:
    import httpx
    from mcp.server.fastmcp import FastMCP

    from floresu_mcp.client import InternalApiClient
    from floresu_mcp.ratelimit import RateLimiter

# The four ground-truth source kinds share the /sources endpoint (narrowed by the
# kind query param); skill and identity_variant have their own endpoints.
_SOURCE_KINDS: dict[ProfileKind, SourceKind] = {
    ProfileKind.ROLE: SourceKind.ROLE,
    ProfileKind.PROJECT: SourceKind.PROJECT,
    ProfileKind.CERTIFICATION: SourceKind.CERTIFICATION,
    ProfileKind.EDUCATION: SourceKind.EDUCATION,
}

# Built once: validate the backend projection into the kind's union member. Members
# carry disjoint required fields, so the union resolves to one concrete shape.
_PROFILE_SUMMARIES: TypeAdapter[list[ProfileSummary]] = TypeAdapter(list[ProfileSummary])
_PROFILE_RECORD: TypeAdapter[ProfileRecord] = TypeAdapter(ProfileRecord)

_PROFILE_LIST = ToolAnnotations(
    title="List profile items of a kind", readOnlyHint=True, openWorldHint=False
)
_PROFILE_GET = ToolAnnotations(title="Get one profile item", readOnlyHint=True, openWorldHint=False)


async def _dispatch_list(
    client: InternalApiClient,
    kind: ProfileKind,
    user_id: str,
    actor: str,
    include_archived: bool,
) -> httpx.Response:
    """The one internal list call for the requested profile kind."""
    source_kind = _SOURCE_KINDS.get(kind)
    if source_kind is not None:
        return await client.sources_list(
            user_id, actor, kind=source_kind.value, include_archived=include_archived
        )
    if kind is ProfileKind.SKILL:
        return await client.skills_list(user_id, actor, include_archived=include_archived)
    return await client.variants_list(user_id, actor, include_archived=include_archived)


async def _dispatch_get(
    client: InternalApiClient, kind: ProfileKind, user_id: str, actor: str, item_id: int
) -> httpx.Response:
    """The one internal single-item call for the requested profile kind."""
    if kind in _SOURCE_KINDS:
        return await client.source_get(user_id, actor, item_id)
    if kind is ProfileKind.SKILL:
        return await client.skill_get(user_id, actor, item_id)
    return await client.variant_get(user_id, actor, item_id)


def register_profile_read_tools(
    mcp: FastMCP, client: InternalApiClient, limiter: RateLimiter
) -> None:
    """Register the parameterized profile read tools onto ``mcp``."""
    tool = counted_tool_registrar(mcp)

    @tool(_PROFILE_LIST)
    async def profile_list(
        kind: ProfileKind, ctx: AgentContext, include_archived: bool = False
    ) -> list[ProfileSummary]:
        """List your profile items of one kind: role, project, certification,
        education, skill, or identity_variant. Set include_archived=true to include
        soft-archived items."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await _dispatch_list(client, kind, user_id, actor, include_archived)
        return _PROFILE_SUMMARIES.validate_python(raise_for_problem(response).json())

    @tool(_PROFILE_GET)
    async def profile_get(kind: ProfileKind, item_id: int, ctx: AgentContext) -> ProfileRecord:
        """Get one profile item of the given kind by id. A source kind (role,
        project, certification, education) returns its typed detail; skill and
        identity_variant return their own shapes."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await _dispatch_get(client, kind, user_id, actor, item_id)
        return _PROFILE_RECORD.validate_python(raise_for_problem(response).json())
