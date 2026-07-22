"""The write MCP tool surface: one ``register_write_tools`` entry point.

Composes the per-domain write-tool registrars (worklog, profile, library, resume,
job application) onto the shared FastMCP server that :mod:`floresu_mcp.app` mounts
behind the bearer-guarded ``/mcp`` prefix, alongside the read surface. Every tool
registers through the one counted registrar
(:func:`~floresu_mcp.tool_registry.counted_tool_registrar`), so each is uniformly
metered, annotated, and schema-preserving.

Agents get archive but never permanent delete: this surface registers no delete,
account-delete, or export tool. Those lifecycle actions are web-human-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu_mcp.tools_jobapp import register_jobapp_write_tools
from floresu_mcp.tools_library_write import register_library_write_tools
from floresu_mcp.tools_profile_write import register_profile_write_tools
from floresu_mcp.tools_resume_write import register_resume_write_tools
from floresu_mcp.tools_worklog_write import register_worklog_write_tools

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from floresu_mcp.client import InternalApiClient
    from floresu_mcp.ratelimit import RateLimiter


def register_write_tools(mcp: FastMCP, client: InternalApiClient, limiter: RateLimiter) -> None:
    """Register the full write tool surface onto ``mcp``.

    Each write tool resolves identity and actor from the validated bearer (never a
    tool argument), checks the rate limit, makes exactly one internal call, and
    maps the response to a lean shape. There is no delete tool: an agent has no
    permanent-delete capability on any entity.
    """
    register_worklog_write_tools(mcp, client, limiter)
    register_profile_write_tools(mcp, client, limiter)
    register_library_write_tools(mcp, client, limiter)
    register_resume_write_tools(mcp, client, limiter)
    register_jobapp_write_tools(mcp, client, limiter)
