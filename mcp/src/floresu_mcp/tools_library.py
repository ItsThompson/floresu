"""Library read tools: list and read canonical bulletpoints.

Each tool is a thin adapter: resolve ``(user_id, actor)`` from the bearer, check
the rate limit, make exactly one internal call, and validate the response into
:class:`~floresu_mcp.schemas_library.BulletpointRecord`. These complement
``search_experience`` (which returns bullet nodes in the scored graph) with a
direct read of a bullet and its provenance edges. Both are ``readOnlyHint``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import ToolAnnotations

from floresu_mcp.config import SCOPE_FULL
from floresu_mcp.schemas_library import BulletpointRecord
from floresu_mcp.scopes import AgentContext, require_scope
from floresu_mcp.tool_errors import raise_for_problem
from floresu_mcp.tool_registry import counted_tool_registrar

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from floresu_mcp.client import InternalApiClient
    from floresu_mcp.ratelimit import RateLimiter

_BULLET_LIST = ToolAnnotations(
    title="List library bulletpoints", readOnlyHint=True, openWorldHint=False
)
_BULLET_GET = ToolAnnotations(
    title="Get one library bulletpoint", readOnlyHint=True, openWorldHint=False
)


def register_library_read_tools(
    mcp: FastMCP, client: InternalApiClient, limiter: RateLimiter
) -> None:
    """Register the library-bullet read tools onto ``mcp``."""
    tool = counted_tool_registrar(mcp)

    @tool(_BULLET_LIST)
    async def bullet_list(
        ctx: AgentContext, include_archived: bool = False
    ) -> list[BulletpointRecord]:
        """List your canonical library bulletpoints with their provenance edges
        (framed source and worklog ids) and usage counts. Set include_archived=true
        to include soft-archived bullets."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await client.bullets_list(user_id, actor, include_archived=include_archived)
        bullets = raise_for_problem(response).json()
        return [BulletpointRecord.model_validate(bullet) for bullet in bullets]

    @tool(_BULLET_GET)
    async def bullet_get(bullet_id: int, ctx: AgentContext) -> BulletpointRecord:
        """Get one canonical bulletpoint by id, with its provenance edges (the
        source and worklog ids it frames), revision token, and usage count."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        response = await client.bullet_get(user_id, actor, bullet_id)
        return BulletpointRecord.model_validate(raise_for_problem(response).json())
