"""MCP server entrypoint (:9000).

Internet-reachable via the tunnel host ``mcp.floresu.com``. Serves the PRM,
validates agent bearer tokens as an OAuth resource server, and forwards tool
calls to the backend internal app. Built from :func:`build_app`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu_mcp.app import build_app
from floresu_mcp.settings import build_rs_settings

if TYPE_CHECKING:
    from fastapi import FastAPI

settings = build_rs_settings()
app: FastAPI = build_app(settings)


def main() -> None:  # pragma: no cover - process entrypoint
    import uvicorn

    uvicorn.run("floresu_mcp.main:app", host=settings.host, port=settings.port)
