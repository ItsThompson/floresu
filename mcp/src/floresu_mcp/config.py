"""MCP resource-server wire-contract constants.

The RS shares NO code with the backend: it is a separate image. The constants
here are therefore a *duplicated domain truth* kept in sync by contract, not by
import. Two groups matter:

- The internal-boundary header names MUST match the backend's
  ``floresu.core.headers`` (``X-User-ID`` / ``X-Actor`` /
  ``X-Internal-Api-Token``): the internal app trusts ``X-User-ID`` only behind a
  valid ``X-Internal-Api-Token`` and reads the named-agent ``X-Actor``.
- The single OAuth scope MUST match the backend AS's ``SCOPE_FULL``
  (``floresu:full``), so the PRM advertises the same access level the AS grants.

Both equalities are mechanically enforced by the cross-package contract tests
(Ticket 22), the only interpreter where the MCP and backend packages import
together; the MCP tests here compare each constant only to itself.
"""

from __future__ import annotations

# Protected Resource Metadata (RFC 9728), served by this RS. The 401 challenge's
# WWW-Authenticate header points clients here so they can discover the AS.
PRM_PATH = "/.well-known/oauth-protected-resource"

# Authorization Server Metadata (RFC 8414), served by the backend AS. The RS
# reads it (built off the pinned issuer) to discover the JWKS URI.
AS_METADATA_PATH = "/.well-known/oauth-authorization-server"

# The MCP transport mount point. Unauthenticated calls under this prefix get a
# 401 + WWW-Authenticate; the tool dispatch sits behind the bearer guard.
MCP_PATH = "/mcp"

# The single full read-write scope. Consent presents exactly one access level;
# every tool requires this one value. MUST equal the backend AS ``SCOPE_FULL``.
SCOPE_FULL = "floresu:full"
SUPPORTED_SCOPES: tuple[str, ...] = (SCOPE_FULL,)

# Bearer methods advertised in the PRM: agents pass the token in the
# Authorization header only, never in the URL (RFC 9728).
BEARER_METHOD_HEADER = "header"

# Internal-boundary headers the RS sends downstream to the backend internal app.
# MUST match floresu.core.headers in the backend (separate image, shared
# contract): the internal app trusts X-User-ID and the named-agent X-Actor only
# behind a valid X-Internal-Api-Token.
USER_ID_HEADER = "X-User-ID"
ACTOR_HEADER = "X-Actor"
INTERNAL_API_TOKEN_HEADER = "X-Internal-Api-Token"

# Correlation id forwarded on every internal call so one agent action is
# traceable across the MCP -> backend hop. Mirrors
# ``floresu.core.correlation.REQUEST_ID_HEADER`` (a correlation convenience,
# never a trust boundary).
REQUEST_ID_HEADER = "X-Request-ID"

# The browser-based MCP Inspector's dev origin. Allowed for CORS only in
# development (see ``RsSettings.allowed_cors_origins``) so its OAuth discovery and
# token-exchange fetches reach this RS; production agents are not browsers.
MCP_INSPECTOR_ORIGIN = "http://localhost:6274"
