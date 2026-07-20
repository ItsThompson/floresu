"""Internal-boundary wire header names, single-sourced.

The three headers that carry identity across the internal trust boundary
(:mod:`floresu.core.identity`, :mod:`floresu.core.actor`). Both apps reference
these names from here so the wire contract has one home and no duplicated string
literals: the external app strips ``X-User-ID`` app-wide (a web client may never
assert an identity), and the internal app trusts these headers behind the shared
token.

These names are also a duplicated wire contract with the out-of-tree MCP client,
which sets them on every internal call. A cross-package contract test pins this
module against the MCP mirror so the two cannot drift.

``X-Request-ID`` is intentionally not here: it is a correlation convenience, never
a trust boundary (see :mod:`floresu.core.correlation`).
"""

from __future__ import annotations

# The trusted caller identity, trusted by the internal app only behind a valid
# INTERNAL_API_TOKEN_HEADER, and stripped app-wide by the external app.
USER_ID_HEADER = "X-User-ID"

# The shared secret that gates the internal boundary. A request without a valid
# value is rejected fail-closed (including when the server has no token set).
INTERNAL_API_TOKEN_HEADER = "X-Internal-Api-Token"

# The actor label at the internal boundary: the calling agent's OAuth client_id,
# set by the MCP server from the validated token (never from a tool argument).
ACTOR_HEADER = "X-Actor"
