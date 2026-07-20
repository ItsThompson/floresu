"""App factory wiring: health, metrics, injected routers/checks/handlers, state,
and the domain-free import boundary."""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from floresu.core.app_factory import create_app
from floresu.core.health import CheckResult
from floresu.core.settings import AppSettings

MakeSettings = Callable[..., AppSettings]

_CORE_DIR = Path(__file__).resolve().parents[1] / "src" / "floresu" / "core"
# The domain packages the core kit must never import (it is wiring only).
_DOMAIN_PACKAGES = frozenset(
    {
        "accounts",
        "oauth",
        "worklog",
        "profile",
        "library",
        "resumes",
        "search",
        "embedding",
        "rendering",
        "storage",
        "audit",
        "jobapps",
    }
)


def test_mounts_health_and_metrics_by_default(make_settings: MakeSettings) -> None:
    client = TestClient(create_app(make_settings()))
    assert client.get("/healthz").status_code == 200
    assert client.get("/metrics").status_code == 200


def test_mounts_injected_routers(make_settings: MakeSettings) -> None:
    router = APIRouter()

    @router.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"pong": True}

    client = TestClient(create_app(make_settings(), routers=[router]))
    assert client.get("/ping").json() == {"pong": True}


def test_wires_injected_readiness_checks(make_settings: MakeSettings) -> None:
    async def db_down() -> CheckResult:
        return CheckResult(name="db", ok=False, detail="down")

    client = TestClient(create_app(make_settings(), readiness_checks=[db_down]))
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"]["db"]["ok"] is False


def test_registers_injected_exception_handlers(make_settings: MakeSettings) -> None:
    class BoomError(Exception):
        pass

    async def handle_boom(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse({"handled": True}, status_code=418)

    router = APIRouter()

    @router.get("/boom")
    async def boom() -> None:
        raise BoomError

    client = TestClient(
        create_app(
            make_settings(),
            routers=[router],
            exception_handlers={BoomError: handle_boom},
        ),
        raise_server_exceptions=False,
    )
    response = client.get("/boom")
    assert response.status_code == 418
    assert response.json() == {"handled": True}


def test_stores_settings_and_logger_on_app_state(make_settings: MakeSettings) -> None:
    settings = make_settings()
    app = create_app(settings)
    assert app.state.settings is settings
    assert app.state.log is not None


def test_core_kit_imports_no_domain_package() -> None:
    # create_app is wiring only: the whole core/ package must import zero domain
    # modules. Parse every core source and assert no `floresu.<domain>` import.
    offenders: list[str] = []
    for source in _CORE_DIR.glob("*.py"):
        tree = ast.parse(source.read_text(), filename=str(source))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            elif isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            for module in modules:
                parts = module.split(".")
                if len(parts) >= 2 and parts[0] == "floresu" and parts[1] in _DOMAIN_PACKAGES:
                    offenders.append(f"{source.name}: {module}")
    assert offenders == [], f"core/ imports domain packages: {offenders}"
