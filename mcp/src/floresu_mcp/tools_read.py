"""The read MCP tool surface: one ``register_read_tools`` entry point.

Composes the per-domain read-tool registrars (worklog, profile, library, resume,
search) onto the shared FastMCP server that :mod:`floresu_mcp.app` mounts behind
the bearer-guarded ``/mcp`` prefix. Every tool registers through the one counted
registrar (:func:`~floresu_mcp.tool_registry.counted_tool_registrar`), so each is
uniformly metered, annotated, and schema-preserving. The write tool surface lands
in a later ticket via a sibling ``register_write_tools`` on the same seam.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu_mcp.tools_library import register_library_read_tools
from floresu_mcp.tools_profile import register_profile_read_tools
from floresu_mcp.tools_resume import register_resume_read_tools
from floresu_mcp.tools_search import register_search_read_tools
from floresu_mcp.tools_worklog import register_worklog_read_tools

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from floresu_mcp.client import InternalApiClient
    from floresu_mcp.ratelimit import RateLimiter


def register_read_tools(mcp: FastMCP, client: InternalApiClient, limiter: RateLimiter) -> None:
    """Register the full read tool surface onto ``mcp``.

    Each read tool resolves identity and actor from the validated bearer (never a
    tool argument), checks the rate limit, makes exactly one internal call, and
    maps the response to a lean read shape.
    """
    register_worklog_read_tools(mcp, client, limiter)
    register_profile_read_tools(mcp, client, limiter)
    register_library_read_tools(mcp, client, limiter)
    register_resume_read_tools(mcp, client, limiter)
    register_search_read_tools(mcp, client, limiter)
