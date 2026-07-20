"""Floresu's own OAuth 2.1 Authorization Server (agent auth).

Mounted on the external app only. Implements Dynamic Client Registration
(RFC 7591), Authorization Code + PKCE (S256), a rotating-refresh token endpoint,
RFC 7009 revocation, RFC 8414 metadata, a JWKS endpoint, and the connected-client
list/revoke surface. The MCP resource server (a later slice) verifies the
audience-bound RS256 access tokens this AS mints via the published JWKS.
"""
