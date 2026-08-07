"""OAuth 2.1 Authorization Server configuration.

Every issuer, metadata, and endpoint URL the AS publishes is built from pinned
deployment config (``public_base_url`` / ``app_public_url`` / ``mcp_public_url``),
never from the request host. This is the highest-risk auth item, the "Site-URL
gotcha": the tunnel reaches the origin as ``http://backend:8000``, so any
request-derived URL would break client issuer/audience validation. All URL
construction therefore lives here and reads only :class:`OAuthConfig`.

Signing is asymmetric: the AS holds an RSA private key; the MCP resource server
verifies via the published JWKS. Access tokens are audience-bound to the MCP
resource. The human HS256 session secret (accounts domain) is kept separate from
this keypair for separate blast radii.

Scope: Floresu grants a single full read-write scope. Consent presents exactly
one access level, so there is no partial-scope state. The MCP resource server
requires this same scope; it is the single value both sides pin.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from floresu.core.settings import AppSettings

# --- Endpoint paths (mounted on the external app) ---------------------------
# The AS metadata document advertises the absolute forms of these, built from
# ``public_base_url``; the router mounts these relative paths.
WELL_KNOWN_AS_METADATA_PATH = "/.well-known/oauth-authorization-server"
JWKS_PATH = "/oauth/jwks"
REGISTER_PATH = "/oauth/register"
AUTHORIZE_PATH = "/oauth/authorize"
AUTHORIZE_CONTEXT_PATH = "/oauth/authorize/context"
AUTHORIZE_DECISION_PATH = "/oauth/authorize/decision"
TOKEN_PATH = "/oauth/token"
REVOKE_PATH = "/oauth/revoke"
CLIENTS_PATH = "/me/clients"

# The SPA route that renders consent: the AS parks the request and 302s the
# browser to ``<app_public_url><CONSENT_ROUTE>?auth_request_id=...``.
CONSENT_ROUTE = "/authorize"

# --- Scope ------------------------------------------------------------------
# A single full read-write scope. Consent presents exactly one access level; the
# MCP resource server pins this same value.
SCOPE_FULL = "floresu:full"
SUPPORTED_SCOPES: tuple[str, ...] = (SCOPE_FULL,)

# PKCE: only S256 is accepted.
CODE_CHALLENGE_METHOD_S256 = "S256"

# Grant/response types the AS supports (public clients + rotating refresh).
GRANT_TYPE_AUTHORIZATION_CODE = "authorization_code"
GRANT_TYPE_REFRESH_TOKEN = "refresh_token"
RESPONSE_TYPE_CODE = "code"
TOKEN_ENDPOINT_AUTH_NONE = "none"  # public clients authenticate via PKCE, not a secret

# Lifetimes for the short-lived server-side artifacts. A parked authorize request
# lives long enough for the human to log in and consent; a code is one-time and
# exchanged immediately, so it is very short.
DEFAULT_AUTH_REQUEST_TTL = timedelta(minutes=10)
DEFAULT_CODE_TTL = timedelta(minutes=1)


@dataclass(frozen=True)
class OAuthConfig:
    """Pinned configuration every OAuth URL and token claim is derived from."""

    issuer: str  # AS origin (also the token ``iss``)
    consent_base_url: str  # SPA origin that renders consent
    resource: str  # the MCP resource; agent access-token ``aud`` (RFC 8707 target)
    key_path: str  # path to the signing private-key PEM ("" -> ephemeral dev key)
    key_id: str  # active signing ``kid``
    access_ttl: timedelta
    refresh_ttl: timedelta
    auth_request_ttl: timedelta = DEFAULT_AUTH_REQUEST_TTL
    code_ttl: timedelta = DEFAULT_CODE_TTL

    def endpoint(self, path: str) -> str:
        """Absolute URL for a mounted path, built from the pinned issuer only."""
        return f"{self.issuer.rstrip('/')}{path}"

    @property
    def consent_url(self) -> str:
        """Absolute SPA consent URL the browser is redirected to after parking."""
        return f"{self.consent_base_url.rstrip('/')}{CONSENT_ROUTE}"

    def canonical_resource(self, requested: str | None) -> str | None:
        """Resolve the RFC 8707 ``resource`` to the one MCP resource we serve.

        A missing ``resource`` defaults to our MCP resource; a provided value must
        match it exactly. A mismatch returns ``None`` so the caller raises
        ``invalid_target`` rather than minting a token for an unknown audience.
        """
        if requested is None or requested == "":
            return self.resource
        return self.resource if requested.rstrip("/") == self.resource.rstrip("/") else None


def build_oauth_config(settings: AppSettings) -> OAuthConfig:
    """Compose the OAuth config from pinned deployment settings."""
    return OAuthConfig(
        issuer=settings.public_base_url,
        consent_base_url=settings.app_public_url,
        resource=settings.mcp_public_url,
        key_path=settings.oauth_private_key_path,
        key_id=settings.oauth_key_id,
        access_ttl=timedelta(seconds=settings.oauth_access_ttl_seconds),
        refresh_ttl=timedelta(seconds=settings.oauth_refresh_ttl_seconds),
    )
