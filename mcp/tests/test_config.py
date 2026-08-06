"""Contract-constant tests: pin the RS's duplicated wire constants.

The RS shares no code with the backend, so these constants are a duplicated
domain truth. These tests pin the exact wire strings the RS emits (header names,
the single scope, discovery paths). The contract tests in ``contract/tests/``
assert equality against the backend; here we only lock the RS-side values so an
accidental rename fails locally too.
"""

from __future__ import annotations

from floresu_mcp import config


def test_internal_boundary_header_names_are_pinned() -> None:
    # MUST match floresu.core.headers in the backend (separate image).
    assert config.USER_ID_HEADER == "X-User-ID"
    assert config.ACTOR_HEADER == "X-Actor"
    assert config.INTERNAL_API_TOKEN_HEADER == "X-Internal-Api-Token"
    assert config.REQUEST_ID_HEADER == "X-Request-ID"


def test_single_full_scope_is_pinned() -> None:
    # MUST match the backend AS SCOPE_FULL.
    assert config.SCOPE_FULL == "floresu:full"
    assert config.SUPPORTED_SCOPES == ("floresu:full",)


def test_discovery_paths_and_transport_prefix_are_pinned() -> None:
    assert config.PRM_PATH == "/.well-known/oauth-protected-resource"
    assert config.AS_METADATA_PATH == "/.well-known/oauth-authorization-server"
    assert config.MCP_PATH == "/mcp"
    assert config.BEARER_METHOD_HEADER == "header"
