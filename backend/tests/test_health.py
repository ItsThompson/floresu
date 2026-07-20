"""Liveness/readiness router: healthz always ok, readyz aggregates checks."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from floresu.core.health import CheckResult, create_health_router


def _client(*checks: object) -> TestClient:
    app = FastAPI()
    app.include_router(create_health_router(checks))  # type: ignore[arg-type]
    return TestClient(app)


def test_healthz_is_always_ok() -> None:
    assert _client().get("/healthz").json() == {"status": "ok"}


def test_readyz_is_ready_with_no_checks() -> None:
    response = _client().get("/readyz")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_readyz_reports_each_passing_check() -> None:
    async def ok() -> CheckResult:
        return CheckResult(name="postgres", ok=True)

    response = _client(ok).get("/readyz")
    assert response.status_code == 200
    assert response.json()["checks"]["postgres"] == {"ok": True, "detail": None}


def test_readyz_returns_503_when_any_check_fails() -> None:
    async def ok() -> CheckResult:
        return CheckResult(name="postgres", ok=True)

    async def down() -> CheckResult:
        return CheckResult(name="redis", ok=False, detail="unreachable")

    response = _client(ok, down).get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["redis"] == {"ok": False, "detail": "unreachable"}


def test_readyz_degrades_a_raising_check_to_503_not_500() -> None:
    async def boom() -> CheckResult:
        raise RuntimeError("probe blew up")

    response = _client(boom).get("/readyz")
    # A misbehaving probe that raises must not mask readiness as a 500.
    assert response.status_code == 503
    assert response.json()["checks"]["check_0"]["ok"] is False
