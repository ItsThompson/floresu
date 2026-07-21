"""Health-router tests: liveness, readiness aggregation, and defensive degrade.

``/healthz`` is always 200; ``/readyz`` runs the injected checks concurrently and
returns 503 if any fails: including a check that *raises*, which degrades to 503
(not 500) so one misbehaving probe cannot mask readiness.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from floresu_mcp.health import CheckResult, create_health_router


def _client(*checks: object) -> TestClient:
    app = FastAPI()
    app.include_router(create_health_router(list(checks)))  # type: ignore[arg-type]
    return TestClient(app)


def test_healthz_is_always_ok() -> None:
    with _client() as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_is_ready_when_all_checks_pass() -> None:
    async def ok() -> CheckResult:
        return CheckResult(name="db", ok=True)

    with _client(ok) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_readyz_is_503_when_a_check_reports_failure() -> None:
    async def down() -> CheckResult:
        return CheckResult(name="db", ok=False, detail="no connection")

    with _client(down) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["checks"]["db"] == {"ok": False, "detail": "no connection"}


def test_readyz_degrades_to_503_when_a_check_raises() -> None:
    async def boom() -> CheckResult:
        raise RuntimeError("probe blew up")

    with _client(boom) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["checks"]["check_0"]["ok"] is False
