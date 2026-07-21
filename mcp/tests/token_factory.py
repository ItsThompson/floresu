"""Test support: mint AS-shaped tokens and serve a fake JWKS discovery.

Keeps the RS tests self-contained (no dependency on the backend AS package, which
ships as a separate image): a throwaway RSA key stands in for the AS signing key,
:func:`public_jwks` is what the RS would fetch, and :func:`make_fetch` fakes the
two discovery hops (AS metadata -> JWKS) the
:class:`~floresu_mcp.keys.RemoteKeyProvider` performs. The token claim shape
mirrors the backend AS ``AccessTokenCodec`` (iss/sub/aud/client_id/scope/exp);
the cross-package contract tests (Ticket 22) hold that mirror honest.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey

from floresu_mcp.config import AS_METADATA_PATH, SCOPE_FULL

if TYPE_CHECKING:
    from floresu_mcp.keys import JsonFetch

ISSUER = "https://app.floresu.test"
RESOURCE = "https://mcp.floresu.test"
JWKS_URI = f"{ISSUER}/oauth/jwks"

_KEY_BITS = 2048


def new_key(kid: str = "kid-test-1") -> RSAKey:
    """A fresh RSA signing key tagged for RS256, mirroring the AS key set."""
    return RSAKey.generate_key(
        _KEY_BITS, parameters={"use": "sig", "alg": "RS256", "kid": kid}, private=True
    )


def public_jwks(*keys: RSAKey) -> dict[str, Any]:
    """The public JWKS document the AS would publish for the given keys."""
    return dict(KeySet(list(keys)).as_dict(private=False))


def mint(
    key: RSAKey,
    *,
    sub: str | None = "user-42",
    issuer: str = ISSUER,
    aud: str = RESOURCE,
    kid: str | None = None,
    client_id: str = "agent-client",
    scope: str = SCOPE_FULL,
    exp_offset: int = 3600,
) -> str:
    """Sign an access token like the AS does (RS256, audience-bound)."""
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": issuer,
        "aud": aud,
        "client_id": client_id,
        "scope": scope,
        "iat": now,
        "exp": now + exp_offset,
        "jti": "jti-test",
    }
    if sub is not None:
        claims["sub"] = sub
    header = {"alg": "RS256", "kid": kid or str(key.kid)}
    return jwt.encode(header, claims, key)


def make_fetch(
    jwks: dict[str, Any], *, issuer: str = ISSUER, jwks_uri: str = JWKS_URI
) -> JsonFetch:
    """A ``JsonFetch`` that serves AS metadata + the given JWKS, tracking calls.

    ``fetch.calls`` records every URL fetched so tests can assert caching (one
    discovery pass) and rotation (a refetch on an unknown ``kid``).
    """
    metadata = {"issuer": issuer, "jwks_uri": jwks_uri}
    calls: list[str] = []

    async def fetch(url: str) -> dict[str, Any]:
        calls.append(url)
        if url == f"{issuer}{AS_METADATA_PATH}":
            return metadata
        if url == jwks_uri:
            return jwks
        raise AssertionError(f"unexpected fetch url: {url}")

    fetch.calls = calls  # type: ignore[attr-defined]
    return fetch
