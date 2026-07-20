"""Unit tests for the access-token codec and refresh-token hashing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from floresu.oauth.tokens import hash_token, mint_refresh_token
from tests.oauth_fakes import MutableClock, build_test_codec, build_test_config, build_test_keyset


def test_minted_access_token_is_audience_bound_and_verifies() -> None:
    config = build_test_config()
    codec = build_test_codec(config, build_test_keyset(config))
    minted = codec.mint(
        subject="user-1", client_id="client-1", scope="floresu:full", audience=config.resource
    )
    verified = codec.verify(minted.token)
    assert verified is not None
    assert verified.subject == "user-1"
    assert verified.client_id == "client-1"
    assert verified.scope == "floresu:full"
    assert verified.audience == config.resource
    assert minted.expires_in == int(config.access_ttl.total_seconds())


def test_token_with_a_foreign_audience_fails_verification() -> None:
    config = build_test_config()
    keyset = build_test_keyset(config)
    codec = build_test_codec(config, keyset)
    # Mint against a different audience than the pinned resource: verify rejects it.
    minted = codec.mint(
        subject="user-1",
        client_id="client-1",
        scope="floresu:full",
        audience="https://evil.example",
    )
    assert codec.verify(minted.token) is None


def test_expired_access_token_fails_against_a_pinned_clock() -> None:
    config = build_test_config(access_ttl=timedelta(minutes=15))
    keyset = build_test_keyset(config)
    clock = MutableClock(datetime(2024, 1, 1, tzinfo=UTC))
    codec = build_test_codec(config, keyset, clock=clock)
    minted = codec.mint(
        subject="user-1", client_id="client-1", scope="floresu:full", audience=config.resource
    )
    assert codec.verify(minted.token) is not None
    clock.advance(timedelta(minutes=16))
    assert codec.verify(minted.token) is None


def test_garbage_token_fails_verification() -> None:
    config = build_test_config()
    codec = build_test_codec(config, build_test_keyset(config))
    assert codec.verify("not-a-jwt") is None


def test_hash_token_is_deterministic_sha256_hex() -> None:
    token = mint_refresh_token()
    assert hash_token(token) == hash_token(token)
    assert len(hash_token(token)) == 64
    assert hash_token("a") != hash_token("b")


def test_mint_refresh_token_is_high_entropy_and_unique() -> None:
    assert mint_refresh_token() != mint_refresh_token()
