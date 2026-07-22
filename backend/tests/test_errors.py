"""Error contract: FloresuError hierarchy + RequestValidationError -> one RFC 9457
problem+json shape, rendered by the single injected handler pair; plus the
catch-all 500 handler and its single structured fault log."""

from __future__ import annotations

from collections.abc import Callable

import pytest
import structlog
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from floresu.core.app_factory import create_app
from floresu.core.errors import (
    Conflict,
    Forbidden,
    NotFound,
    Unauthorized,
    Validation,
    Violation,
    build_exception_handlers,
)
from floresu.core.settings import AppSettings

MakeSettings = Callable[..., AppSettings]


class _Item(BaseModel):
    title: str


def _client() -> TestClient:
    app = FastAPI()
    for key, handler in build_exception_handlers().items():
        app.add_exception_handler(key, handler)

    router = APIRouter()

    @router.get("/not-found")
    async def not_found() -> None:
        raise NotFound("no resume resume-7f3k")

    @router.get("/forbidden")
    async def forbidden() -> None:
        raise Forbidden("not your resume")

    @router.get("/unauthorized")
    async def unauthorized() -> None:
        raise Unauthorized("no session")

    @router.get("/conflict")
    async def conflict() -> None:
        raise Conflict("The record changed under you; re-read and retry.")

    @router.get("/validation")
    async def validation() -> None:
        raise Validation(
            "1 structural rule failed.",
            violations=[Violation(rule="V1_ACYCLIC", ids=["a", "b"], message="cycle")],
        )

    @router.get("/validation-fields")
    async def validation_fields() -> None:
        raise Validation("registration failed", fields={"email": "already registered"})

    @router.post("/items")
    async def create_item(item: _Item) -> dict[str, bool]:
        return {"ok": True}

    app.include_router(router)
    return TestClient(app)


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("/not-found", 404, "NOT_FOUND"),
        ("/forbidden", 403, "FORBIDDEN"),
        ("/unauthorized", 401, "UNAUTHORIZED"),
        ("/conflict", 409, "CONFLICT"),
        ("/validation", 422, "VALIDATION"),
    ],
)
def test_each_error_maps_to_its_status_and_code(path: str, status: int, code: str) -> None:
    response = _client().get(path)

    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["status"] == status
    assert body["code"] == code
    assert body["type"].endswith(f"/{code.lower().replace('_', '-')}")
    assert body["type"].startswith("https://floresu.com/errors/")
    assert body["title"]
    assert body["detail"]
    assert body["instance"] == path


def test_validation_carries_violations_array() -> None:
    body = _client().get("/validation").json()
    assert body["violations"] == [{"rule": "V1_ACYCLIC", "ids": ["a", "b"], "message": "cycle"}]
    assert "fields" not in body


def test_validation_can_carry_a_field_map_without_violations() -> None:
    body = _client().get("/validation-fields").json()
    assert body["fields"] == {"email": "already registered"}
    assert "violations" not in body


def test_plain_conflict_has_no_extension_members_on_the_wire() -> None:
    body = _client().get("/conflict").json()
    assert "violations" not in body
    assert "fields" not in body


def test_request_validation_error_uses_the_same_field_map_shape() -> None:
    response = _client().post("/items", json={})

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "VALIDATION"
    assert body["type"] == "https://floresu.com/errors/validation"
    assert "body.title" in body["fields"]
    assert "violations" not in body


# --- catch-all 500 handler ---------------------------------------------

_LEAKY_DETAIL = "secret internal detail: db dsn postgres://admin:hunter2@host"


def _boom_router() -> APIRouter:
    router = APIRouter()

    @router.get("/boom")
    async def boom() -> None:
        raise RuntimeError(_LEAKY_DETAIL)

    return router


def test_unhandled_exception_renders_generic_500_problem_json(make_settings: MakeSettings) -> None:
    app = create_app(
        make_settings(),
        routers=[_boom_router()],
        exception_handlers=build_exception_handlers(),
    )
    response = TestClient(app, raise_server_exceptions=False).get("/boom")

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "https://floresu.com/errors/internal",
        "title": "Internal server error",
        "status": 500,
        "code": "INTERNAL",
        "detail": "An unexpected error occurred.",
        "instance": "/boom",
    }


def test_unhandled_exception_leaks_no_internal_detail(make_settings: MakeSettings) -> None:
    app = create_app(
        make_settings(),
        routers=[_boom_router()],
        exception_handlers=build_exception_handlers(),
    )
    raw = TestClient(app, raise_server_exceptions=False).get("/boom").text

    assert "hunter2" not in raw
    assert _LEAKY_DETAIL not in raw
    assert "RuntimeError" not in raw
    assert "Traceback" not in raw


def _bare_boom_client() -> TestClient:
    app = FastAPI()
    for key, handler in build_exception_handlers().items():
        app.add_exception_handler(key, handler)
    app.include_router(_boom_router())
    return TestClient(app, raise_server_exceptions=False)


def test_unhandled_exception_emits_exactly_one_error_log_with_exc_info_and_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cap = structlog.testing.CapturingLogger()
    monkeypatch.setattr("floresu.core.errors._log", cap)

    _bare_boom_client().get("/boom")

    error_calls = [call for call in cap.calls if call.method_name == "error"]
    assert len(error_calls) == 1
    assert error_calls[0].args == ("unhandled_exception",)
    assert error_calls[0].kwargs["path"] == "/boom"
    assert isinstance(error_calls[0].kwargs["exc_info"], RuntimeError)


def test_routine_4xx_does_not_hit_the_fault_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    cap = structlog.testing.CapturingLogger()
    monkeypatch.setattr("floresu.core.errors._log", cap)

    _client().get("/not-found")

    # A routine 4xx renders via handle_floresu_error and never reaches the fault log.
    assert cap.calls == []
