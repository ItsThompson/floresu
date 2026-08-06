"""Resume write tools: create, edit the document, manage items, finalize, and render.

Each tool is a thin adapter: resolve ``(user_id, actor)`` from the bearer, check
the rate limit, make exactly one internal call, and validate the response. Every
mutation of an existing resume carries the resume's current ``revision`` as
``if_match_revision`` (forwarded as the ``If-Match`` header); the backend rejects
a stale revision as a recoverable conflict, so the agent re-reads and retries
rather than silently overwriting a concurrent change. ``resume_create`` mirrors
the backend creation contract (``kind`` + ``source`` + ``job_application_id``
for an application). ``resume_finalize`` freezes an application resume;
``resume_render`` renders the resume to a persisted PDF and returns a reference the
user can open. Resume writes carry no embeddable content of their own (they
reference canonical bullets), so none count against the embed-write budget.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import ToolAnnotations

from floresu_mcp.config import SCOPE_FULL
from floresu_mcp.schemas_resume import ResumeRecord
from floresu_mcp.schemas_resume_write import (
    AddItemInput,
    FinalizeResult,
    RenderReference,
    ResumeCreateInput,
    ResumeReorderInput,
    ResumeUpdateInput,
)
from floresu_mcp.scopes import AgentContext, require_scope
from floresu_mcp.tool_errors import raise_for_problem
from floresu_mcp.tool_registry import counted_tool_registrar

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from floresu_mcp.client import InternalApiClient
    from floresu_mcp.ratelimit import RateLimiter

_RESUME_CREATE = ToolAnnotations(
    title="Create a resume",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)
_RESUME_UPDATE = ToolAnnotations(
    title="Update a resume document",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
_RESUME_ITEM_ADD = ToolAnnotations(
    title="Add a resume item",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)
_RESUME_ITEM_REMOVE = ToolAnnotations(
    title="Remove a resume item",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
_RESUME_ITEM_REORDER = ToolAnnotations(
    title="Reorder resume sections/items",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
_RESUME_FINALIZE = ToolAnnotations(
    title="Finalize an application resume",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)
_RESUME_RENDER = ToolAnnotations(
    title="Render a resume to a PDF",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def register_resume_write_tools(
    mcp: FastMCP, client: InternalApiClient, limiter: RateLimiter
) -> None:
    """Register the resume write tools onto ``mcp``."""
    tool = counted_tool_registrar(mcp)

    @tool(_RESUME_CREATE)
    async def resume_create(request: ResumeCreateInput, ctx: AgentContext) -> ResumeRecord:
        """Create a resume. kind ('living' or 'application') sets the result and is
        never inferred from source; source is where the initial content comes from
        (blank, from_resume, or duplicate). job_application_id is required for an
        application resume and rejected for a living one. Returns the created
        resume."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await client.resume_create(user_id, actor, request.model_dump(mode="json"))
        return ResumeRecord.model_validate(raise_for_problem(response).json())

    @tool(_RESUME_UPDATE)
    async def resume_update(
        resume_id: int, document: ResumeUpdateInput, if_match_revision: int, ctx: AgentContext
    ) -> ResumeRecord:
        """Overwrite a resume's document: title, template, identity-variant header,
        and ordered sections. Carry the resume's current revision as
        if_match_revision. Returns the updated resume."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await client.resume_update(
            user_id, actor, resume_id, document.model_dump(mode="json"), if_match=if_match_revision
        )
        return ResumeRecord.model_validate(raise_for_problem(response).json())

    @tool(_RESUME_ITEM_ADD)
    async def resume_item_add(
        resume_id: int, request: AddItemInput, if_match_revision: int, ctx: AgentContext
    ) -> ResumeRecord:
        """Append one item to a resume section: a library_ref (a canonical bullet id)
        or a local inline item. Carry the resume's current revision as
        if_match_revision. Returns the updated resume."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await client.resume_add_item(
            user_id, actor, resume_id, request.model_dump(mode="json"), if_match=if_match_revision
        )
        return ResumeRecord.model_validate(raise_for_problem(response).json())

    @tool(_RESUME_ITEM_REMOVE)
    async def resume_item_remove(
        resume_id: int, item_id: str, if_match_revision: int, ctx: AgentContext
    ) -> ResumeRecord:
        """Remove an item from a resume (the item is dropped from the document; a
        referenced canonical bullet is not deleted). Carry the resume's current
        revision as if_match_revision. Returns the updated resume."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await client.resume_remove_item(
            user_id, actor, resume_id, item_id, if_match=if_match_revision
        )
        return ResumeRecord.model_validate(raise_for_problem(response).json())

    @tool(_RESUME_ITEM_REORDER)
    async def resume_item_reorder(
        resume_id: int, order: ResumeReorderInput, if_match_revision: int, ctx: AgentContext
    ) -> ResumeRecord:
        """Reorder a resume's sections and/or the items within sections, addressed by
        id (each list is a full permutation of its set). Carry the resume's current
        revision as if_match_revision. Returns the updated resume."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await client.resume_reorder(
            user_id, actor, resume_id, order.model_dump(mode="json"), if_match=if_match_revision
        )
        return ResumeRecord.model_validate(raise_for_problem(response).json())

    @tool(_RESUME_FINALIZE)
    async def resume_finalize(resume_id: int, ctx: AgentContext) -> FinalizeResult:
        """Freeze an application resume: resolve every library reference to inline
        read-only text, snapshot the identity, render and store the frozen PDF, and
        submit a linked job application. Only application resumes can finalize.
        Returns what was frozen and the stored PDF key."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await client.resume_finalize(user_id, actor, resume_id)
        return FinalizeResult.model_validate(raise_for_problem(response).json())

    @tool(_RESUME_RENDER)
    async def resume_render(resume_id: int, ctx: AgentContext) -> RenderReference:
        """Render a resume to a PDF, store it, and return a reference (object key plus
        a time-limited download URL) the user can open."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await client.resume_render(user_id, actor, resume_id)
        return RenderReference.model_validate(raise_for_problem(response).json())
