"""Search read tool: the one ``search_experience`` tool.

Hybrid search over the user's corpus (worklog + sources + canonical bullets),
returning the flat RRF-ranked list and the same hits rolled into the scored
provenance DAG, so the agent reconstructs the hierarchy in one call. The tool is a
thin adapter: resolve ``(user_id, actor)`` from the bearer, check the rate limit,
make exactly one internal call (``POST /search``), and validate the response into
:class:`~floresu_mcp.schemas_search.SearchResult`. It is ``readOnlyHint``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import ToolAnnotations

from floresu_mcp.config import SCOPE_FULL
from floresu_mcp.schemas_search import SearchFilters, SearchResult
from floresu_mcp.scopes import AgentContext, require_scope
from floresu_mcp.tool_errors import raise_for_problem
from floresu_mcp.tool_registry import counted_tool_registrar

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from floresu_mcp.client import InternalApiClient
    from floresu_mcp.ratelimit import RateLimiter

_SEARCH_EXPERIENCE = ToolAnnotations(
    title="Search experience", readOnlyHint=True, openWorldHint=False
)


def register_search_read_tools(
    mcp: FastMCP, client: InternalApiClient, limiter: RateLimiter
) -> None:
    """Register the ``search_experience`` tool onto ``mcp``."""
    tool = counted_tool_registrar(mcp)

    @tool(_SEARCH_EXPERIENCE)
    async def search_experience(
        query: str, ctx: AgentContext, filters: SearchFilters | None = None
    ) -> SearchResult:
        """Search your career history and get back both a flat relevance-ranked
        list and the scored provenance graph (sources, worklog entries, and
        bullets with their edges), so you can see which sources matter and what
        sits under each without a second call. Optional filters narrow the corpus;
        filtering by kinds returns matching source nodes (not the accomplishments
        under them), so to reach those search the source's text or narrow by
        source_ids."""
        user_id, actor = require_scope(ctx, SCOPE_FULL)
        await limiter.check(user_id)
        applied = filters or SearchFilters()
        body = {"query": query, "filters": applied.model_dump(mode="json", by_alias=True)}
        response = await client.search(user_id, actor, body)
        return SearchResult.model_validate(raise_for_problem(response).json())
