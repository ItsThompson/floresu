"""The web-only lifecycle surface is absent from the internal (agent) app.

Permanent delete, data export, and account deletion are human-web-only. This test
pins the enforcement half of "archive-not-delete everywhere; permanent delete is
web-human-only": the external app exposes the lifecycle routes, and the internal
app exposes none of them. It also strengthens the earlier no-web-only-route guard
by asserting the internal (agent) app exposes zero ``DELETE`` routes and no
``/account`` surface at all, so no agent can ever reach a destructive path.
"""

from __future__ import annotations

from floresu.api.main import app as external_app
from floresu.api_internal.main import app as internal_app
from floresu.core.route_registry import RouteKey, mounted_product_routes

_LIFECYCLE_ROUTES = {
    RouteKey("DELETE", "/worklog/{worklog_id}"),
    RouteKey("DELETE", "/sources/{source_id}"),
    RouteKey("DELETE", "/bullets/{bullet_id}"),
    RouteKey("DELETE", "/resumes/{resume_id}"),
    RouteKey("GET", "/account/export"),
    RouteKey("DELETE", "/account"),
}


def test_external_app_exposes_every_lifecycle_route() -> None:
    mounted = set(mounted_product_routes(external_app))
    missing = _LIFECYCLE_ROUTES - mounted
    assert missing == set(), f"external app is missing lifecycle routes: {missing}"


def test_internal_app_exposes_no_lifecycle_route() -> None:
    mounted = set(mounted_product_routes(internal_app))
    leaked = _LIFECYCLE_ROUTES & mounted
    assert leaked == set(), f"internal (agent) app leaks web-only routes: {leaked}"


def test_internal_app_exposes_no_delete_route_at_all() -> None:
    # The agent-facing app reserves DELETE for the web-only surface, so it exposes
    # none: an agent gets archive (a soft, restorable state), never a hard delete.
    deletes = [key for key in mounted_product_routes(internal_app) if key.method == "DELETE"]
    assert deletes == [], f"internal app unexpectedly exposes DELETE routes: {deletes}"


def test_internal_app_exposes_no_account_surface() -> None:
    account_routes = [
        key for key in mounted_product_routes(internal_app) if key.path.startswith("/account")
    ]
    assert account_routes == [], f"internal app exposes account routes: {account_routes}"
