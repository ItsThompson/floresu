"""Route -> access-level coverage: every mounted product route must have a
declared level, an undeclared route fails safe (deny), and both real apps are
fully covered (today: no product routes, so trivially covered)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, FastAPI

from floresu.api.main import app as external_app
from floresu.api_internal.main import app as internal_app
from floresu.core.app_factory import create_app
from floresu.core.route_registry import (
    EXTERNAL_ROUTE_ACCESS,
    INTERNAL_ROUTE_ACCESS,
    AccessLevel,
    RouteKey,
    RouteRegistry,
    mounted_product_routes,
    verify_route_coverage,
)
from floresu.core.settings import AppSettings

MakeSettings = Callable[..., AppSettings]

_RESUME_ROUTE = RouteKey(method="GET", path="/resumes/{resume_id}")


def _app_with_resume_route() -> FastAPI:
    router = APIRouter()

    @router.get("/resumes/{resume_id}")
    async def get_resume(resume_id: str) -> dict[str, str]:
        return {"id": resume_id}

    app = FastAPI()
    app.include_router(router)
    return app


def test_undeclared_mounted_route_fails_coverage() -> None:
    report = verify_route_coverage(_app_with_resume_route(), {})
    assert not report.is_covered
    assert _RESUME_ROUTE in report.undeclared


def test_declared_route_passes_coverage() -> None:
    registry: RouteRegistry = {_RESUME_ROUTE: AccessLevel.EXTERNAL_COOKIE}
    report = verify_route_coverage(_app_with_resume_route(), registry)
    assert report.is_covered
    assert report.undeclared == []


def test_orphaned_declaration_is_reported() -> None:
    registry: RouteRegistry = {
        _RESUME_ROUTE: AccessLevel.EXTERNAL_COOKIE,
        RouteKey(method="DELETE", path="/resumes/{resume_id}"): AccessLevel.EXTERNAL_COOKIE,
    }
    report = verify_route_coverage(_app_with_resume_route(), registry)
    assert not report.is_covered
    assert RouteKey(method="DELETE", path="/resumes/{resume_id}") in report.orphaned


def test_enumerates_product_routes_from_the_api_surface() -> None:
    # Only the real HTTP method appears; auto-added HEAD/OPTIONS are not in the
    # OpenAPI surface, so they are not treated as access-controlled routes.
    assert mounted_product_routes(_app_with_resume_route()) == [_RESUME_ROUTE]


def test_infra_and_docs_routes_need_no_declaration(make_settings: MakeSettings) -> None:
    # A factory-built app mounts only health, metrics, and docs: no product routes.
    app = create_app(make_settings())
    assert mounted_product_routes(app) == []
    assert verify_route_coverage(app, {}).is_covered


def test_real_external_app_has_full_route_coverage() -> None:
    report = verify_route_coverage(external_app, EXTERNAL_ROUTE_ACCESS)
    assert report.is_covered, f"external app has undeclared routes: {report.undeclared}"


def test_real_internal_app_has_full_route_coverage() -> None:
    report = verify_route_coverage(internal_app, INTERNAL_ROUTE_ACCESS)
    assert report.is_covered, f"internal app has undeclared routes: {report.undeclared}"
