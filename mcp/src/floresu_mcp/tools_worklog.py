"""Worklog read tools: query the timeline, read one entry, list tags.

Each tool is a thin adapter: it resolves ``(user_id, actor)`` from the validated
bearer (:func:`require_scope`, never a tool argument), checks the per-token rate
limit, makes exactly one internal call via
:class:`~floresu_mcp.client.InternalApiClient`, and validates the response into a
lean read shape. Backend failures surface as model-recoverable
:class:`ToolError`\\s (:mod:`floresu_mcp.tool_errors`). All three are annotated
``readOnlyHint``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import ToolAnnotations

from floresu_mcp.config import SCOPE_FULL
from floresu_mcp.schemas import Tag, WorklogEntryRecord, WorklogEntrySummary
from floresu_mcp.scopes import AgentContext, require_scope
from floresu_mcp.tool_errors import raise_for_problem
from floresu_mcp.tool_registry import counted_tool_registrar

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from floresu_mcp.client import InternalApiClient
    from floresu_mcp.ratelimit import RateLimiter

_WORKLOG_QUERY = ToolAnnotations(
    title="Query worklog entries", readOnlyHint=True, openWorldHint=False
)
_WORKLOG_GET = ToolAnnotations(
    title="Get one worklog entry", readOnlyHint=True, openWorldHint=False
)
_LIST_TAGS = ToolAnnotations(title="List tag labels", readOnlyHint=True, openWorldHint=False)


def register_worklog_read_tools(
    mcp: FastMCP, client: InternalApiClient, limiter: RateLimiter
) -> None:
    """Register the worklog read tools onto ``mcp``."""
    tool = counted_tool_registrar(mcp)

    @tool(_WORKLOG_QUERY)
    async def worklog_query(
        ctx: AgentContext, include_archived: bool = False
    ) -> list[WorklogEntrySummary]:
        """List your worklog entries as lean timeline rows (title, date, tags, and
        attached source ids). Set include_archived=true to include soft-archived
        entries."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await client.worklog_list(user_id, actor, include_archived=include_archived)
        entries = raise_for_problem(response).json()
        return [WorklogEntrySummary.model_validate(entry) for entry in entries]

    @tool(_WORKLOG_GET)
    async def worklog_get(worklog_id: int, ctx: AgentContext) -> WorklogEntryRecord:
        """Get one worklog entry by id, with its tags, attached source ids, and the
        ids of the canonical bullets that frame it."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await client.worklog_get(user_id, actor, worklog_id)
        return WorklogEntryRecord.model_validate(raise_for_problem(response).json())

    @tool(_LIST_TAGS)
    async def list_tags(ctx: AgentContext) -> list[Tag]:
        """List your existing tag labels so you can reuse one rather than minting a
        near-duplicate when tagging a worklog entry."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await client.list_tags(user_id, actor)
        tags = raise_for_problem(response).json()
        return [Tag.model_validate(tag) for tag in tags]
