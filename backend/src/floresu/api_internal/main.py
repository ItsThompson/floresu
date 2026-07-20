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

from floresu.audit.wiring import build_write_event_publisher
from floresu.core.actor import resolve_internal_actor
from floresu.core.app_factory import create_app
from floresu.core.db import create_database, create_db_lifespan, db_readiness_check
from floresu.core.errors import build_exception_handlers
from floresu.core.identity import require_internal_user
from floresu.core.settings import INTERNAL_PORT, INTERNAL_SERVICE, build_app_settings
from floresu.profile.router import create_sources_router
from floresu.profile.wiring import build_source_service_provider

if TYPE_CHECKING:
    from fastapi import FastAPI

settings = build_app_settings(service=INTERNAL_SERVICE, port=INTERNAL_PORT)
db = create_database(settings.database_url)

# Product routers, mounted with the trusted-header identity and the named-agent
# actor. The same routers mount on the external app with the human boundary; the
# service, transaction, and write-event publish live once in the domain layer.
sources_router = create_sources_router(
    build_source_service_provider(),
    identity=require_internal_user,
    actor=resolve_internal_actor,
)

app: FastAPI = create_app(
    settings,
    routers=[sources_router],
    readiness_checks=[db_readiness_check(db.engine)],
    exception_handlers=build_exception_handlers(),
    lifespan=create_db_lifespan(db.engine),
)
app.state.db = db
# The write-event seam, composed with the audit consumer as the sole transactional
# consumer. The internal app's domain slices publish agent writes through this.
app.state.events = build_write_event_publisher()


def main() -> None:  # pragma: no cover - process entrypoint
    import uvicorn

    uvicorn.run("floresu.api_internal.main:app", host=settings.host, port=settings.port)
