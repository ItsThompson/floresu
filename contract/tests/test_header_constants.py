"""The header-constant contract test: internal-boundary names and the OAuth scope.

The MCP server sets the internal-boundary headers on every call to the backend
internal API, and the backend trusts them behind the shared token. The two packages
share no code, so each re-declares the names; this test pins them equal across the
packages (a rename on one side fails) and to their exact wire values (a coordinated
rename must update this contract deliberately). The single OAuth scope is pinned the
same way, so the MCP PRM advertises exactly the access level the backend AS grants.

``X-Request-ID`` is a correlation convenience, not a trust-boundary header, so on the
backend it lives in ``core.correlation`` rather than ``core.headers``; the MCP client
still forwards it on every internal call, so it is pinned here too.
"""

from __future__ import annotations

from floresu.core import correlation as be_correlation
from floresu.core import headers as be_headers
from floresu.oauth import config as be_oauth
from floresu_mcp import config as mcp_config


def test_user_id_header_matches_across_packages() -> None:
    assert mcp_config.USER_ID_HEADER == be_headers.USER_ID_HEADER == "X-User-ID"


def test_actor_header_matches_across_packages() -> None:
    assert mcp_config.ACTOR_HEADER == be_headers.ACTOR_HEADER == "X-Actor"


def test_internal_api_token_header_matches_across_packages() -> None:
    assert (
        mcp_config.INTERNAL_API_TOKEN_HEADER
        == be_headers.INTERNAL_API_TOKEN_HEADER
        == "X-Internal-Api-Token"
    )


def test_request_id_header_matches_across_packages() -> None:
    assert mcp_config.REQUEST_ID_HEADER == be_correlation.REQUEST_ID_HEADER == "X-Request-ID"


def test_full_scope_matches_across_packages() -> None:
    assert mcp_config.SCOPE_FULL == be_oauth.SCOPE_FULL == "floresu:full"


def test_supported_scopes_match_across_packages() -> None:
    assert mcp_config.SUPPORTED_SCOPES == be_oauth.SUPPORTED_SCOPES == ("floresu:full",)
