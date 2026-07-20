"""Correlation middleware: per-request request_id bound into structlog contextvars."""

from __future__ import annotations

import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient

from floresu.core.correlation import REQUEST_ID_HEADER, CorrelationMiddleware, _inbound_request_id


def _bound_request_id_app() -> FastAPI:
    app = FastAPI()

    @app.get("/echo")
    async def echo() -> dict[str, object]:
        return {"ctx": structlog.contextvars.get_contextvars()}

    app.add_middleware(CorrelationMiddleware, service="floresu-test")
    return app


def test_mints_a_request_id_and_binds_the_service() -> None:
    ctx = TestClient(_bound_request_id_app()).get("/echo").json()["ctx"]
    assert ctx["service"] == "floresu-test"
    # A fresh id is a 32-char lowercase hex uuid.
    assert len(ctx["request_id"]) == 32


def test_honors_a_valid_inbound_request_id() -> None:
    ctx = (
        TestClient(_bound_request_id_app())
        .get("/echo", headers={REQUEST_ID_HEADER: "trace-abc_123"})
        .json()["ctx"]
    )
    assert ctx["request_id"] == "trace-abc_123"


def test_drops_a_malformed_inbound_id_and_mints_a_fresh_one() -> None:
    ctx = (
        TestClient(_bound_request_id_app())
        .get("/echo", headers={REQUEST_ID_HEADER: "bad id with spaces"})
        .json()["ctx"]
    )
    # A value outside the token shape is not propagated; a fresh id is minted.
    assert ctx["request_id"] != "bad id with spaces"
    assert len(ctx["request_id"]) == 32


def test_inbound_request_id_reads_the_scope_header() -> None:
    header = REQUEST_ID_HEADER.lower().encode("latin-1")
    assert _inbound_request_id({"headers": [(header, b"abc123")]}) == "abc123"
    assert _inbound_request_id({"headers": [(header, b"")]}) is None
    assert _inbound_request_id({"headers": []}) is None
