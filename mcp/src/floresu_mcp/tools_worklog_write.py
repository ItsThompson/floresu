"""Worklog write tools: create, update, and archive entries.

Each tool is a thin adapter: it resolves ``(user_id, actor)`` from the validated
bearer (:func:`require_scope`, never a tool argument), checks the rate limit,
makes exactly one internal call via
:class:`~floresu_mcp.client.InternalApiClient`, and validates the response into
:class:`~floresu_mcp.schemas.WorklogEntryRecord`. Create and update change content
that triggers embedding, so they count against the tighter embed-write budget;
archive is a soft, reversible state change and does not. Backend failures surface
as model-recoverable :class:`ToolError`\\s (:mod:`floresu_mcp.tool_errors`).

Tag add/remove is expressed through the full-representation ``tags`` list on
create/update (set semantics): the backend reconciles the entry's tag edges to
exactly the submitted labels, so there is no separate one-call tag mutation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import ToolAnnotations

from floresu_mcp.config import SCOPE_FULL
from floresu_mcp.schemas import WorklogEntryInput, WorklogEntryRecord
from floresu_mcp.scopes import AgentContext, require_scope
from floresu_mcp.tool_errors import raise_for_problem
from floresu_mcp.tool_registry import counted_tool_registrar

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from floresu_mcp.client import InternalApiClient
    from floresu_mcp.ratelimit import RateLimiter

_WORKLOG_CREATE = ToolAnnotations(
    title="Create worklog entry",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)
_WORKLOG_UPDATE = ToolAnnotations(
    title="Update worklog entry",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
_WORKLOG_ARCHIVE = ToolAnnotations(
    title="Archive worklog entry",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def register_worklog_write_tools(
    mcp: FastMCP, client: InternalApiClient, limiter: RateLimiter
) -> None:
    """Register the worklog write tools onto ``mcp``."""
    tool = counted_tool_registrar(mcp)

    @tool(_WORKLOG_CREATE)
    async def worklog_create(entry: WorklogEntryInput, ctx: AgentContext) -> WorklogEntryRecord:
        """Create a worklog entry with a title and date, optionally a description,
        tags, and attached source ids. Returns the created entry with its framing
        bullets."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id, embed_write=True)
        response = await client.worklog_create(user_id, actor, entry.model_dump(mode="json"))
        return WorklogEntryRecord.model_validate(raise_for_problem(response).json())

    @tool(_WORKLOG_UPDATE)
    async def worklog_update(
        worklog_id: int, entry: WorklogEntryInput, ctx: AgentContext
    ) -> WorklogEntryRecord:
        """Overwrite a worklog entry's title, date, description, tags, and attached
        sources (full representation: the tags and source_ids you send become the
        entry's exact sets). Returns the updated entry."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id, embed_write=True)
        response = await client.worklog_update(
            user_id, actor, worklog_id, entry.model_dump(mode="json")
        )
        return WorklogEntryRecord.model_validate(raise_for_problem(response).json())

    @tool(_WORKLOG_ARCHIVE)
    async def worklog_archive(worklog_id: int, ctx: AgentContext) -> WorklogEntryRecord:
        """Soft-archive a worklog entry so it drops from active reads. This is
        reversible from the web app; agents cannot permanently delete an entry.
        Returns the archived entry."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await client.worklog_archive(user_id, actor, worklog_id)
        return WorklogEntryRecord.model_validate(raise_for_problem(response).json())
