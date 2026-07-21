"""PRM document + WWW-Authenticate challenge tests.

The PRM (RFC 9728) advertises the AS issuer and the single supported scope, built
from pinned config; the 401 challenge points at it.
"""

from __future__ import annotations

from floresu_mcp.config import SCOPE_FULL
from floresu_mcp.prm import (
    build_prm_document,
    prm_resource_metadata_url,
    www_authenticate_challenge,
)

_RESOURCE = "https://mcp.floresu.test"
_ISSUER = "https://app.floresu.test"


def test_prm_advertises_the_as_issuer_and_single_scope() -> None:
    document = build_prm_document(resource=_RESOURCE, issuer=_ISSUER)

    assert document["resource"] == _RESOURCE
    assert document["authorization_servers"] == [_ISSUER]
    assert document["scopes_supported"] == [SCOPE_FULL]
    assert document["bearer_methods_supported"] == ["header"]


def test_resource_metadata_url_is_built_from_the_pinned_resource() -> None:
    assert (
        prm_resource_metadata_url("https://mcp.floresu.test/")
        == "https://mcp.floresu.test/.well-known/oauth-protected-resource"
    )


def test_challenge_points_at_the_prm_document() -> None:
    challenge = www_authenticate_challenge(_RESOURCE)

    assert challenge == (
        'Bearer resource_metadata="https://mcp.floresu.test/.well-known/oauth-protected-resource"'
    )
