"""Library write tools: create, scope-edit, archive, and promote canonical bullets.

Each tool is a thin adapter: resolve ``(user_id, actor)`` from the bearer, check
the rate limit, make exactly one internal call, and validate the response.
``bullet_update`` is the copy-on-write scope edit: unlike the web boundary, the
agent MUST state ``scope`` (``this_resume`` or ``everywhere``) and carry the
matching ``If-Match`` revision (the canonical bullet revision for ``everywhere``,
the resume revision for ``this_resume``); the backend rejects a stale revision as
a recoverable conflict. Creating a bullet and promoting a local item both mint
canonical, embeddable text, so they count against the tighter embed-write budget;
an ``everywhere`` scope edit re-embeds the canonical bullet, so it counts too,
while a ``this_resume`` fork writes non-embedded local text and does not.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import ToolAnnotations
from pydantic import TypeAdapter

from floresu_mcp.config import SCOPE_FULL
from floresu_mcp.schemas_library import BulletpointRecord
from floresu_mcp.schemas_library_write import (
    BulletpointInput,
    ResumeEditScope,
    ScopeEditInput,
    ScopeEditResult,
)
from floresu_mcp.schemas_resume import ResumeRecord
from floresu_mcp.scopes import AgentContext, require_scope
from floresu_mcp.tool_errors import raise_for_problem
from floresu_mcp.tool_registry import counted_tool_registrar

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from floresu_mcp.client import InternalApiClient
    from floresu_mcp.ratelimit import RateLimiter

_SCOPE_EDIT_RESULT: TypeAdapter[ScopeEditResult] = TypeAdapter(ScopeEditResult)

_BULLET_CREATE = ToolAnnotations(
    title="Create a library bullet",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)
_BULLET_UPDATE = ToolAnnotations(
    title="Edit a library bullet (scoped)",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
_BULLET_ARCHIVE = ToolAnnotations(
    title="Archive a library bullet",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
_BULLET_PROMOTE = ToolAnnotations(
    title="Promote a resume-local item to a library bullet",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)


def register_library_write_tools(
    mcp: FastMCP, client: InternalApiClient, limiter: RateLimiter
) -> None:
    """Register the library write tools onto ``mcp``."""
    tool = counted_tool_registrar(mcp)

    @tool(_BULLET_CREATE)
    async def bullet_create(bullet: BulletpointInput, ctx: AgentContext) -> BulletpointRecord:
        """Create a canonical library bulletpoint with its provenance edges (the
        source and worklog ids it frames). Returns the created bullet."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id, embed_write=True)
        response = await client.bullet_create(user_id, actor, bullet.model_dump(mode="json"))
        return BulletpointRecord.model_validate(raise_for_problem(response).json())

    @tool(_BULLET_UPDATE)
    async def bullet_update(edit: ScopeEditInput, ctx: AgentContext) -> ScopeEditResult:
        """Edit the text of a canonical bullet a resume item resolves to. You MUST
        state scope: 'everywhere' edits the canonical bullet (every resume that
        references it updates; carry if_match_bullet_revision) or 'this_resume'
        forks a resume-local copy leaving the canonical bullet unchanged (carry
        resume_id and if_match_resume_revision). Returns the edited bullet
        ('everywhere') or the updated resume ('this_resume')."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        embed_write = edit.scope is ResumeEditScope.EVERYWHERE
        await limiter.check(user_id, embed_write=embed_write)
        response = await client.bullet_scope_edit(user_id, actor, edit.model_dump(mode="json"))
        return _SCOPE_EDIT_RESULT.validate_python(raise_for_problem(response).json())

    @tool(_BULLET_ARCHIVE)
    async def bullet_archive(bullet_id: int, ctx: AgentContext) -> BulletpointRecord:
        """Soft-archive a canonical bulletpoint. This is reversible from the web app;
        agents cannot permanently delete a bullet. Returns the archived bullet."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await client.bullet_archive(user_id, actor, bullet_id)
        return BulletpointRecord.model_validate(raise_for_problem(response).json())

    @tool(_BULLET_PROMOTE)
    async def bullet_promote(
        resume_id: int, item_id: str, if_match_resume_revision: int, ctx: AgentContext
    ) -> ResumeRecord:
        """Promote a resume-local item (a copy-on-write fork or a net-new inline item)
        to a canonical library bullet, so it becomes reusable and searchable. Carry
        the resume's current revision as if_match_resume_revision. Returns the
        updated resume with the item swapped to a library reference."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id, embed_write=True)
        response = await client.bullet_promote(
            user_id, actor, resume_id, item_id, if_match=if_match_resume_revision
        )
        return ResumeRecord.model_validate(raise_for_problem(response).json())
