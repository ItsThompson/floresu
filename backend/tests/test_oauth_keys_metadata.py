"""Unit tests for signing keys, the published JWKS, and RFC 8414 metadata."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from joserfc.jwk import RSAKey

from floresu.oauth.config import OAuthConfig
from floresu.oauth.keys import load_signing_key_set
from floresu.oauth.metadata import build_as_metadata
from tests.oauth_fakes import build_test_config, build_test_keyset


def test_ephemeral_dev_key_is_generated_when_no_pem_is_configured() -> None:
    config = build_test_config()
    keyset = load_signing_key_set(config, is_dev=True)
    assert keyset.active_kid == "test-kid"


def test_mounted_pem_is_loaded_and_publishes_a_public_jwks(tmp_path: Path) -> None:
    # The production path: a private-key PEM is mounted on disk and loaded under
    # the configured kid, then publishes a public-only JWKS.
    pem_path = tmp_path / "oauth-signing-key.pem"
    pem_path.write_bytes(RSAKey.generate_key(2048, private=True).as_pem(private=True))
    config = OAuthConfig(
        issuer="https://api.floresu.app",
        consent_base_url="https://floresu.app",
        resource="https://mcp.floresu.app",
        key_path=str(pem_path),
        key_id="prod-kid",
        access_ttl=timedelta(minutes=15),
        refresh_ttl=timedelta(days=30),
    )
    keyset = load_signing_key_set(config, is_dev=False)
    assert keyset.active_kid == "prod-kid"
    (key,) = keyset.jwks()["keys"]
    assert key["kid"] == "prod-kid"
    assert "d" not in key


def test_missing_key_outside_development_fails_fast() -> None:
    config = build_test_config()
    with pytest.raises(RuntimeError, match="OAUTH_PRIVATE_KEY_PATH"):
        load_signing_key_set(config, is_dev=False)


def test_jwks_publishes_public_material_only() -> None:
    keyset = build_test_keyset(build_test_config())
    jwks = keyset.jwks()
    (key,) = jwks["keys"]
    assert key["kty"] == "RSA"
    assert key["kid"] == "test-kid"
    # The private exponent must never leave via the JWKS.
    assert "d" not in key


def test_signing_header_binds_the_active_kid() -> None:
    keyset = build_test_keyset(build_test_config())
    assert keyset.signing_header() == {"alg": "RS256", "kid": "test-kid"}


def test_metadata_advertises_endpoints_scope_and_s256_only() -> None:
    config = build_test_config()
    metadata = build_as_metadata(config)
    assert metadata["issuer"] == "https://api.floresu.app"
    assert metadata["token_endpoint"] == "https://api.floresu.app/oauth/token"
    assert metadata["jwks_uri"] == "https://api.floresu.app/oauth/jwks"
    assert metadata["registration_endpoint"] == "https://api.floresu.app/oauth/register"
    assert metadata["revocation_endpoint"] == "https://api.floresu.app/oauth/revoke"
    assert metadata["code_challenge_methods_supported"] == ["S256"]
    assert metadata["token_endpoint_auth_methods_supported"] == ["none"]
    assert metadata["scopes_supported"] == ["floresu:full"]
    assert metadata["grant_types_supported"] == ["authorization_code", "refresh_token"]
