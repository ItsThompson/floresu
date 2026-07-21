"""Correlation-middleware tests.

The RS is the origin of an agent action, so it always mints a fresh
``request_id`` and never honors an inbound one. The middleware is pure-ASGI, so
the binding lives in the request's own context and is visible downstream.
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient

from floresu_mcp.correlation import CorrelationMiddleware
from floresu_mcp.settings import SERVICE


def _app_echoing_correlation() -> FastAPI:
    app = FastAPI()
    app.add_middleware(CorrelationMiddleware, service=SERVICE)

    @app.get("/echo")
    async def echo() -> dict[str, str | None]:
        ctx = structlog.contextvars.get_contextvars()
        return {"request_id": ctx.get("request_id"), "service": ctx.get("service")}

    return app


def test_mints_a_fresh_request_id_bound_with_the_service() -> None:
    with TestClient(_app_echoing_correlation()) as client:
        body = client.get("/echo").json()

    assert body["service"] == SERVICE
    assert body["request_id"] is not None
    assert len(body["request_id"]) == 32  # uuid4 hex


def test_inbound_request_id_is_never_honored() -> None:
    # The RS is internet-facing; an agent-supplied X-Request-ID must not become
    # the correlation id (unlike the backend, which honors an inbound id).
    with TestClient(_app_echoing_correlation()) as client:
        body = client.get("/echo", headers={"X-Request-ID": "attacker-supplied"}).json()

    assert body["request_id"] != "attacker-supplied"


def test_each_request_gets_a_distinct_id() -> None:
    with TestClient(_app_echoing_correlation()) as client:
        first = client.get("/echo").json()["request_id"]
        second = client.get("/echo").json()["request_id"]

    assert first != second
