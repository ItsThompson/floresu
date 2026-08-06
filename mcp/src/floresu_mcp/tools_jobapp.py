"""Job-application tools: the read pair and the writes.

The read tools ``jobapp_list`` / ``jobapp_get`` and the write tools
``jobapp_create`` / ``jobapp_update`` are the whole MCP job-application surface
over the internal API. Each tool is a thin adapter: resolve ``(user_id, actor)``
from the bearer, check the rate limit, make exactly one internal call, and
validate the response into
:class:`~floresu_mcp.schemas_jobapp.JobApplicationSummary`.

Setting the status to ``submitted`` via ``jobapp_update`` is the P0 finalize
trigger: the backend finalizes the linked 1:1 application resume, and rejects the
submit with a recoverable error when no resume is linked. Job applications carry
no embeddable content, so no write counts against the embed-write budget.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import ToolAnnotations

from floresu_mcp.config import SCOPE_FULL
from floresu_mcp.schemas_jobapp import (
    JobApplicationCreateInput,
    JobApplicationSummary,
    JobApplicationUpdateInput,
)
from floresu_mcp.scopes import AgentContext, require_scope
from floresu_mcp.tool_errors import raise_for_problem
from floresu_mcp.tool_registry import counted_tool_registrar

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from floresu_mcp.client import InternalApiClient
    from floresu_mcp.ratelimit import RateLimiter

_JOBAPP_LIST = ToolAnnotations(
    title="List job applications", readOnlyHint=True, openWorldHint=False
)
_JOBAPP_GET = ToolAnnotations(
    title="Get one job application", readOnlyHint=True, openWorldHint=False
)
_JOBAPP_CREATE = ToolAnnotations(
    title="Create a job application",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)
_JOBAPP_UPDATE = ToolAnnotations(
    title="Update a job application",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def register_jobapp_read_tools(
    mcp: FastMCP, client: InternalApiClient, limiter: RateLimiter
) -> None:
    """Register the job-application read tools onto ``mcp``."""
    tool = counted_tool_registrar(mcp)

    @tool(_JOBAPP_LIST)
    async def jobapp_list(ctx: AgentContext) -> list[JobApplicationSummary]:
        """List your job applications (company, role title, status, and the id of the
        1:1 linked application resume)."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await client.jobapp_list(user_id, actor)
        applications = raise_for_problem(response).json()
        return [JobApplicationSummary.model_validate(app) for app in applications]

    @tool(_JOBAPP_GET)
    async def jobapp_get(application_id: int, ctx: AgentContext) -> JobApplicationSummary:
        """Get one job application by id, with the id of its 1:1 linked application
        resume (null when none is linked yet)."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await client.jobapp_get(user_id, actor, application_id)
        return JobApplicationSummary.model_validate(raise_for_problem(response).json())


def register_jobapp_write_tools(
    mcp: FastMCP, client: InternalApiClient, limiter: RateLimiter
) -> None:
    """Register the job-application write tools onto ``mcp``."""
    tool = counted_tool_registrar(mcp)

    @tool(_JOBAPP_CREATE)
    async def jobapp_create(
        request: JobApplicationCreateInput, ctx: AgentContext
    ) -> JobApplicationSummary:
        """Create a job application from a company and role title; the status starts
        'added'. Returns the created application."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await client.jobapp_create(user_id, actor, request.model_dump(mode="json"))
        return JobApplicationSummary.model_validate(raise_for_problem(response).json())

    @tool(_JOBAPP_UPDATE)
    async def jobapp_update(
        application_id: int, request: JobApplicationUpdateInput, ctx: AgentContext
    ) -> JobApplicationSummary:
        """Edit a job application's company/role title and/or set its status. Setting
        status='submitted' finalizes the linked application resume; it is rejected
        with a recoverable error when no resume is linked (the status stays 'added').
        Returns the updated application."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        # Partial write: drop unset fields so an omitted company/role_title is not
        # sent as a null the backend would have to interpret.
        response = await client.jobapp_update(
            user_id, actor, application_id, request.model_dump(mode="json", exclude_none=True)
        )
        return JobApplicationSummary.model_validate(raise_for_problem(response).json())
