"""The cookie session verifier behind the identity seam.

Tests the composition without a database: the revocation lookup is injected, so
the verifier is exercised directly against the codec plus a controllable
blacklist.
"""

from __future__ import annotations

from floresu.accounts.session import RevocationLookup, create_session_verifier
from tests.accounts_fakes import build_test_codec


def _revocation_lookup(revoked: set[str]) -> RevocationLookup:
    async def is_revoked(sid: str) -> bool:
        return sid in revoked

    return is_revoked


async def test_verifier_resolves_a_valid_access_cookie_to_the_user_id() -> None:
    codec = build_test_codec()
    verify = create_session_verifier(codec, _revocation_lookup(set()))
    pair = codec.mint_pair("42")
    assert await verify(pair.access_token) == "42"


async def test_verifier_rejects_a_revoked_session() -> None:
    codec = build_test_codec()
    pair = codec.mint_pair("42")
    verify = create_session_verifier(codec, _revocation_lookup({pair.sid}))
    # A blacklisted sid stops resolving even though the access token is unexpired.
    assert await verify(pair.access_token) is None


async def test_verifier_rejects_a_garbage_cookie() -> None:
    verify = create_session_verifier(build_test_codec(), _revocation_lookup(set()))
    assert await verify("not-a-jwt") is None


async def test_verifier_rejects_a_refresh_token_at_the_access_boundary() -> None:
    # Only an access token resolves a session; presenting the refresh token as the
    # session cookie must not authenticate.
    codec = build_test_codec()
    verify = create_session_verifier(codec, _revocation_lookup(set()))
    pair = codec.mint_pair("42")
    assert await verify(pair.refresh_token) is None
