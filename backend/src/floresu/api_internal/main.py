"""Internal app entrypoint (:8001).

Never tunnel-routed and never host-published: reachable in-network by first-party
``app-net`` containers only (the MCP server is its intended caller). The
composition root for the trusted-header surface the agent path calls. Built from
the shared factory with the internal service identity injected, differing from the
external app only by these settings; the trusted-header identity boundary is
layered on by the internal-boundary slice.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.core.app_factory import create_app
from floresu.core.db import create_database, create_db_lifespan, db_readiness_check
from floresu.core.errors import build_exception_handlers
from floresu.core.settings import INTERNAL_PORT, INTERNAL_SERVICE, build_app_settings

if TYPE_CHECKING:
    from fastapi import FastAPI

settings = build_app_settings(service=INTERNAL_SERVICE, port=INTERNAL_PORT)
db = create_database(settings.database_url)

app: FastAPI = create_app(
    settings,
    readiness_checks=[db_readiness_check(db.engine)],
    exception_handlers=build_exception_handlers(),
    lifespan=create_db_lifespan(db.engine),
)
app.state.db = db


def main() -> None:  # pragma: no cover - process entrypoint
    import uvicorn

    uvicorn.run("floresu.api_internal.main:app", host=settings.host, port=settings.port)
