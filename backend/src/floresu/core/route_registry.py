"""Declarative route -> access-level registry with fail-safe coverage.

Every mounted product route must have a declared access level. A coverage test
(``tests/test_route_registry.py``) compares the mounted routes against the
registries below and **fails safe (deny)** if any mounted route has no entry, so
an unscoped endpoint cannot ship.

The registries are declared centrally and separately from where routers are
mounted, on purpose: forgetting to declare a route is exactly what the coverage
test catches. The same path can carry different access levels on the two apps, so
the registries are per-app. They start empty: the two apps mount only the health
and metrics infra routes today (excluded by construction), and each domain slice
adds its product routes here as it lands.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI


class AccessLevel(StrEnum):
    """How a route resolves and gates identity."""

    PUBLIC = "public"  # no authentication (landing, well-known metadata)
    EXTERNAL_COOKIE = "external-cookie"  # require_user (human session cookie)
    INTERNAL_TRUSTED = "internal-trusted"  # require_internal_user (trusted X-User-ID)
    OAUTH = "oauth"  # OAuth 2.1 bearer / AS handshake endpoints


@dataclass(frozen=True, order=True)
class RouteKey:
    """A mounted route identified by method + matched path template."""

    method: str
    path: str


RouteRegistry = Mapping[RouteKey, AccessLevel]

# Declarative per-app registries. Product routes are declared here by the module
# that mounts them. The coverage test fails safe (deny) the moment a mounted
# product route is missing an entry. The sources domain is the first slice mounted
# on the internal app, so its routes populate the internal registry too.
EXTERNAL_ROUTE_ACCESS: RouteRegistry = {
    # Human web auth. The session-establishing endpoints are PUBLIC (they resolve
    # identity from credentials or the refresh cookie, not a prior session);
    # GET /me requires a resolved session cookie.
    RouteKey("POST", "/auth/register"): AccessLevel.PUBLIC,
    RouteKey("POST", "/auth/login"): AccessLevel.PUBLIC,
    RouteKey("POST", "/auth/refresh"): AccessLevel.PUBLIC,
    RouteKey("POST", "/auth/logout"): AccessLevel.PUBLIC,
    RouteKey("GET", "/me"): AccessLevel.EXTERNAL_COOKIE,
    # Agent OAuth 2.1 Authorization Server (mounted on the external app only). The
    # discovery + handshake endpoints are OAUTH (no human session; the client is
    # PKCE/token-authenticated or the metadata is public discovery). The consent
    # decision and connected-client management require the human session cookie.
    RouteKey("GET", "/.well-known/oauth-authorization-server"): AccessLevel.OAUTH,
    RouteKey("GET", "/oauth/jwks"): AccessLevel.OAUTH,
    RouteKey("POST", "/oauth/register"): AccessLevel.OAUTH,
    RouteKey("GET", "/oauth/authorize"): AccessLevel.OAUTH,
    RouteKey("GET", "/oauth/authorize/context"): AccessLevel.OAUTH,
    RouteKey("POST", "/oauth/authorize/decision"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("POST", "/oauth/token"): AccessLevel.OAUTH,
    RouteKey("POST", "/oauth/revoke"): AccessLevel.OAUTH,
    RouteKey("GET", "/me/clients"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("DELETE", "/me/clients/{client_id}"): AccessLevel.EXTERNAL_COOKIE,
    # Profile sources (roles/projects/certs/education). The web boundary resolves
    # the human session cookie; the same routes are mounted on the internal app
    # for the agent path (below).
    RouteKey("POST", "/sources"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("GET", "/sources"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("POST", "/sources/reorder"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("GET", "/sources/{source_id}"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("PUT", "/sources/{source_id}"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("POST", "/sources/{source_id}/archive"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("POST", "/sources/{source_id}/restore"): AccessLevel.EXTERNAL_COOKIE,
    # Worklog entries, tags, and source attachment. The web boundary resolves the
    # human session cookie; the same routes mount on the internal app (below).
    RouteKey("POST", "/worklog"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("GET", "/worklog"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("GET", "/worklog/tags"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("GET", "/worklog/{worklog_id}"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("PUT", "/worklog/{worklog_id}"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("POST", "/worklog/{worklog_id}/archive"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("POST", "/worklog/{worklog_id}/restore"): AccessLevel.EXTERNAL_COOKIE,
    # Canonical library bulletpoints and the provenance DAG. The web boundary
    # resolves the human session cookie; the same routes mount on the internal app
    # for the agent path (below).
    RouteKey("POST", "/bullets"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("GET", "/bullets"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("GET", "/bullets/{bullet_id}"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("PUT", "/bullets/{bullet_id}"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("POST", "/bullets/{bullet_id}/archive"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("POST", "/bullets/{bullet_id}/restore"): AccessLevel.EXTERNAL_COOKIE,
    # Curated skills (name + derived usage count). The web boundary resolves the
    # human session cookie; the same routes mount on the internal app (below).
    RouteKey("POST", "/skills"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("GET", "/skills"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("POST", "/skills/reorder"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("GET", "/skills/{skill_id}"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("PUT", "/skills/{skill_id}"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("POST", "/skills/{skill_id}/archive"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("POST", "/skills/{skill_id}/restore"): AccessLevel.EXTERNAL_COOKIE,
    # Identity variants (labeled contact sets with a named default). No reorder:
    # variants are unordered; the default is set via PUT. The same routes mount on
    # the internal app (below).
    RouteKey("POST", "/identity-variants"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("GET", "/identity-variants"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("GET", "/identity-variants/{variant_id}"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("PUT", "/identity-variants/{variant_id}"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("POST", "/identity-variants/{variant_id}/archive"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("POST", "/identity-variants/{variant_id}/restore"): AccessLevel.EXTERNAL_COOKIE,
    # Resumes: the JSONB-authoritative Output layer. The web boundary resolves the
    # human session cookie; the same routes mount on the internal app (below).
    RouteKey("POST", "/resumes"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("GET", "/resumes"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("GET", "/resumes/{resume_id}"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("PUT", "/resumes/{resume_id}"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("POST", "/resumes/{resume_id}/items"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("POST", "/resumes/{resume_id}/items/{item_id}/remove"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("POST", "/resumes/{resume_id}/reorder"): AccessLevel.EXTERNAL_COOKIE,
    # Copy-on-write scoped bullet edit and promote (resume item <-> canonical bullet).
    RouteKey("POST", "/resumes/bullet-edit"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("POST", "/resumes/{resume_id}/items/{item_id}/promote"): AccessLevel.EXTERNAL_COOKIE,
    # Live activity feed (external app only): the SSE stream and the initial-load
    # read both require the human session cookie.
    RouteKey("GET", "/feed"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey("GET", "/feed/history"): AccessLevel.EXTERNAL_COOKIE,
}
INTERNAL_ROUTE_ACCESS: RouteRegistry = {
    # Profile sources on the agent-facing internal app: trusted-header identity.
    RouteKey("POST", "/sources"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("GET", "/sources"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("POST", "/sources/reorder"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("GET", "/sources/{source_id}"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("PUT", "/sources/{source_id}"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("POST", "/sources/{source_id}/archive"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("POST", "/sources/{source_id}/restore"): AccessLevel.INTERNAL_TRUSTED,
    # Worklog on the agent-facing internal app: trusted-header identity.
    RouteKey("POST", "/worklog"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("GET", "/worklog"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("GET", "/worklog/tags"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("GET", "/worklog/{worklog_id}"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("PUT", "/worklog/{worklog_id}"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("POST", "/worklog/{worklog_id}/archive"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("POST", "/worklog/{worklog_id}/restore"): AccessLevel.INTERNAL_TRUSTED,
    # Canonical library bulletpoints on the agent-facing internal app: trusted-header identity.
    RouteKey("POST", "/bullets"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("GET", "/bullets"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("GET", "/bullets/{bullet_id}"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("PUT", "/bullets/{bullet_id}"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("POST", "/bullets/{bullet_id}/archive"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("POST", "/bullets/{bullet_id}/restore"): AccessLevel.INTERNAL_TRUSTED,
    # Curated skills on the agent-facing internal app: trusted-header identity.
    RouteKey("POST", "/skills"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("GET", "/skills"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("POST", "/skills/reorder"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("GET", "/skills/{skill_id}"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("PUT", "/skills/{skill_id}"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("POST", "/skills/{skill_id}/archive"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("POST", "/skills/{skill_id}/restore"): AccessLevel.INTERNAL_TRUSTED,
    # Identity variants on the agent-facing internal app: trusted-header identity.
    RouteKey("POST", "/identity-variants"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("GET", "/identity-variants"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("GET", "/identity-variants/{variant_id}"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("PUT", "/identity-variants/{variant_id}"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("POST", "/identity-variants/{variant_id}/archive"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("POST", "/identity-variants/{variant_id}/restore"): AccessLevel.INTERNAL_TRUSTED,
    # Resumes on the agent-facing internal app: trusted-header identity.
    RouteKey("POST", "/resumes"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("GET", "/resumes"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("GET", "/resumes/{resume_id}"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("PUT", "/resumes/{resume_id}"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("POST", "/resumes/{resume_id}/items"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("POST", "/resumes/{resume_id}/items/{item_id}/remove"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("POST", "/resumes/{resume_id}/reorder"): AccessLevel.INTERNAL_TRUSTED,
    # Copy-on-write scoped bullet edit and promote (resume item <-> canonical bullet).
    RouteKey("POST", "/resumes/bullet-edit"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("POST", "/resumes/{resume_id}/items/{item_id}/promote"): AccessLevel.INTERNAL_TRUSTED,
    # Embedding pipeline (internal app only): the arq worker reads an item's text
    # and writes its vector back over these trusted-header routes. Purge is a POST
    # (not a DELETE): the agent-facing internal app exposes no DELETE routes.
    RouteKey("GET", "/embed/items/{kind}/{item_id}"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("PUT", "/embed/items/{kind}/{item_id}"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey("POST", "/embed/items/{kind}/{item_id}/purge"): AccessLevel.INTERNAL_TRUSTED,
}


# OpenAPI operation keys that are HTTP methods (a path item also carries non-method
# keys such as "parameters").
_HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})


def mounted_product_routes(app: FastAPI) -> list[RouteKey]:
    """Every access-controlled route on ``app``, read from its OpenAPI document.

    The product/API surface is exactly the OpenAPI paths. Framework and infra
    endpoints (liveness, readiness, the metrics scrape, the docs) are mounted with
    ``include_in_schema=False`` and so are excluded by construction; only real
    product endpoints (which clients and codegen also consume) require a declared
    access level.
    """
    paths: dict[str, Any] = app.openapi().get("paths", {})
    keys: list[RouteKey] = []
    for path, operations in paths.items():
        for method in operations:
            if method.lower() in _HTTP_METHODS:
                keys.append(RouteKey(method=method.upper(), path=path))
    return keys


@dataclass(frozen=True)
class CoverageReport:
    """Result of cross-checking mounted routes against a registry."""

    undeclared: list[RouteKey]  # mounted but no declared level -> DENY (coverage fails)
    orphaned: list[RouteKey]  # declared but not mounted -> stale registry entry

    @property
    def is_covered(self) -> bool:
        return not self.undeclared and not self.orphaned


def verify_route_coverage(app: FastAPI, registry: RouteRegistry) -> CoverageReport:
    """Compare mounted routes against ``registry`` in both directions.

    ``undeclared`` (mounted without a declared level) is the security-critical,
    fail-safe-deny direction; ``orphaned`` (declared but never bound) catches a
    stale or mistyped registry entry.
    """
    mounted = mounted_product_routes(app)
    mounted_set = set(mounted)
    undeclared = sorted(key for key in mounted if key not in registry)
    orphaned = sorted(key for key in registry if key not in mounted_set)
    return CoverageReport(undeclared=undeclared, orphaned=orphaned)
