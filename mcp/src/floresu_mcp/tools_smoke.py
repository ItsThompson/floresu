"""Smoke tools that prove the RS path end to end.

Two workflow-shaped tools: one read (``worklog_list``) and one write
(``worklog_create``): registered on the shared FastMCP server that
:mod:`floresu_mcp.app` mounts under the bearer-guarded ``/mcp`` prefix. They
exist to prove the whole foundation path an agent hits (bearer boundary ->
identity + actor on the request -> scope gate -> rate limit -> one internal call
-> lean output), not to be the tool surface: the full read/write tools land in
later tickets, registered onto this same seam.

Each tool is a **thin adapter**: it resolves ``(user_id, actor)`` from the
validated bearer (:func:`require_scope`, never a tool argument), checks the rate
limit, makes exactly one internal call via
:class:`~floresu_mcp.client.InternalApiClient`, and validates the response into a
lean projection. ``worklog_create`` writes content that triggers embedding, so it
counts against the tighter embed-write budget. Backend failures surface as
model-recoverable :class:`ToolError`\\s (:mod:`floresu_mcp.tool_errors`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import ToolAnnotations

from floresu_mcp.config import SCOPE_FULL
from floresu_mcp.schemas import WorklogEntryInput, WorklogEntrySummary
from floresu_mcp.scopes import AgentContext, require_scope
from floresu_mcp.tool_errors import raise_for_problem
from floresu_mcp.tool_registry import counted_tool_registrar

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from floresu_mcp.client import InternalApiClient
    from floresu_mcp.ratelimit import RateLimiter

_WORKLOG_LIST = ToolAnnotations(
    title="List worklog entries", readOnlyHint=True, openWorldHint=False
)
_WORKLOG_CREATE = ToolAnnotations(
    title="Create worklog entry",
    readOnlyHint=False,
    destructiveHint=False,
    openWorldHint=False,
)


def register_smoke_tools(mcp: FastMCP, client: InternalApiClient, limiter: RateLimiter) -> None:
    """Register the read + write smoke tools onto ``mcp``.

    Each closes over the injected internal client and rate limiter; the full tool
    surfaces register onto this same server in later tickets.
    """
    tool = counted_tool_registrar(mcp)

    @tool(_WORKLOG_LIST)
    async def worklog_list(
        ctx: AgentContext, include_archived: bool = False
    ) -> list[WorklogEntrySummary]:
        """List your worklog entries, most-relevant fields only. Set
        include_archived=true to include soft-archived entries."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await client.worklog_list(user_id, actor, include_archived=include_archived)
        entries = raise_for_problem(response).json()
        return [WorklogEntrySummary.model_validate(entry) for entry in entries]

    @tool(_WORKLOG_CREATE)
    async def worklog_create(entry: WorklogEntryInput, ctx: AgentContext) -> WorklogEntrySummary:
        """Create a worklog entry with a title and date, optionally a description,
        tags, and attached source ids. Returns the created entry."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id, embed_write=True)
        response = await client.worklog_create(user_id, actor, entry.model_dump(mode="json"))
        return WorklogEntrySummary.model_validate(raise_for_problem(response).json())
