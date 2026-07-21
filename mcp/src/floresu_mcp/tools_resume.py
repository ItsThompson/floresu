"""Resume read tools: list resumes, read one, and list render templates.

Each tool is a thin adapter: resolve ``(user_id, actor)`` from the bearer, check
the rate limit, make exactly one internal call, and validate the response into a
lean read shape. ``resume_list`` returns living and application summaries;
``resume_get`` returns one resume with its full document; ``list_templates``
returns the global render-template registry. All three are ``readOnlyHint``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import ToolAnnotations

from floresu_mcp.config import SCOPE_FULL
from floresu_mcp.schemas_render import TemplateInfo
from floresu_mcp.schemas_resume import ResumeKind, ResumeRecord, ResumeSummary
from floresu_mcp.scopes import AgentContext, require_scope
from floresu_mcp.tool_errors import raise_for_problem
from floresu_mcp.tool_registry import counted_tool_registrar

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from floresu_mcp.client import InternalApiClient
    from floresu_mcp.ratelimit import RateLimiter

_RESUME_LIST = ToolAnnotations(title="List resumes", readOnlyHint=True, openWorldHint=False)
_RESUME_GET = ToolAnnotations(title="Get one resume", readOnlyHint=True, openWorldHint=False)
_LIST_TEMPLATES = ToolAnnotations(
    title="List render templates", readOnlyHint=True, openWorldHint=False
)


def register_resume_read_tools(
    mcp: FastMCP, client: InternalApiClient, limiter: RateLimiter
) -> None:
    """Register the resume + template read tools onto ``mcp``."""
    tool = counted_tool_registrar(mcp)

    @tool(_RESUME_LIST)
    async def resume_list(
        ctx: AgentContext, kind: ResumeKind | None = None, include_archived: bool = False
    ) -> list[ResumeSummary]:
        """List your resumes as summaries (no document body). Pass kind=living or
        kind=application to filter; set include_archived=true to include
        soft-archived resumes."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await client.resumes_list(
            user_id,
            actor,
            kind=kind.value if kind is not None else None,
            include_archived=include_archived,
        )
        resumes = raise_for_problem(response).json()
        return [ResumeSummary.model_validate(resume) for resume in resumes]

    @tool(_RESUME_GET)
    async def resume_get(resume_id: int, ctx: AgentContext) -> ResumeRecord:
        """Get one resume by id, with its full versioned document: header, template,
        and ordered sections of library-ref and resume-local items."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await client.resume_get(user_id, actor, resume_id)
        return ResumeRecord.model_validate(raise_for_problem(response).json())

    @tool(_LIST_TEMPLATES)
    async def list_templates(ctx: AgentContext) -> list[TemplateInfo]:
        """List the available global render templates (id, name, description) you
        can select when creating or rendering a resume."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await client.list_templates(user_id, actor)
        templates = raise_for_problem(response).json()
        return [TemplateInfo.model_validate(template) for template in templates]
