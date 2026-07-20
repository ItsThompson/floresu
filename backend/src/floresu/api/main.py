"""External app entrypoint (:8000).

Internet-reachable via the Cloudflare tunnel. The composition root that hosts the
public REST surface for the human web client. Built from the shared factory with
the external service identity injected; the human session boundary, identity
strip, and CORS are layered on by the web-auth slice.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.core.app_factory import create_app
from floresu.core.db import create_database, create_db_lifespan, db_readiness_check
from floresu.core.errors import build_exception_handlers
from floresu.core.settings import EXTERNAL_PORT, EXTERNAL_SERVICE, build_app_settings

if TYPE_CHECKING:
    from fastapi import FastAPI

settings = build_app_settings(service=EXTERNAL_SERVICE, port=EXTERNAL_PORT)
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

    uvicorn.run("floresu.api.main:app", host=settings.host, port=settings.port)
