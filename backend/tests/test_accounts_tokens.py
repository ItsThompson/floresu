"""Session token codec: mint/verify, type separation, and clock-pinned expiry."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tests.accounts_fakes import MutableClock, build_test_codec


def test_mint_pair_shares_one_sid_and_reports_max_ages() -> None:
    codec = build_test_codec(access_ttl=timedelta(minutes=15), refresh_ttl=timedelta(days=14))
    pair = codec.mint_pair("42")
    assert pair.access_token and pair.refresh_token
    assert pair.access_max_age == 15 * 60
    assert pair.refresh_max_age == 14 * 24 * 60 * 60
    # The access and refresh tokens of one pair share the session id.
    access = codec.verify_access(pair.access_token)
    refresh = codec.verify_refresh(pair.refresh_token)
    assert access is not None and refresh is not None
    assert access.sid == refresh.sid == pair.sid
    assert access.user_id == refresh.user_id == "42"


def test_an_access_token_does_not_verify_as_a_refresh_token() -> None:
    # The token type is part of the contract: an access token cannot be replayed
    # at the refresh endpoint and vice versa.
    codec = build_test_codec()
    pair = codec.mint_pair("7")
    assert codec.verify_refresh(pair.access_token) is None
    assert codec.verify_access(pair.refresh_token) is None


def test_a_tampered_or_foreign_token_does_not_verify() -> None:
    codec = build_test_codec()
    other = build_test_codec()  # same secret, so forge with a different secret
    assert codec.verify_access("garbage.token.value") is None
    # A token signed by a codec with a different secret must not verify.
    from pydantic import SecretStr

    from floresu.accounts.config import SessionConfig
    from floresu.accounts.tokens import SessionTokenCodec

    foreign_secret = SecretStr("a-different-secret-0123456789xyz!")
    foreign = SessionTokenCodec(SessionConfig(secret=foreign_secret))
    assert other.verify_access(foreign.mint_pair("1").access_token) is None


def test_expiry_is_measured_against_the_injected_clock() -> None:
    clock = MutableClock(datetime(2024, 1, 1, tzinfo=UTC))
    codec = build_test_codec(access_ttl=timedelta(minutes=15), clock=clock)
    pair = codec.mint_pair("9")
    assert codec.verify_access(pair.access_token) is not None  # valid at t0

    clock.advance(timedelta(minutes=16))  # past the access TTL
    assert codec.verify_access(pair.access_token) is None
