"""JWKS discovery + caching tests for :class:`RemoteKeyProvider`.

The provider discovers the JWKS URI from AS metadata (RFC 8414), fetches the
public keys, caches them, and refetches once (throttled) on an unknown ``kid``.
Only the network is faked (:func:`make_fetch`), which records every URL so the
caching and rotation behaviors are asserted by call count.
"""

from __future__ import annotations

from floresu_mcp.config import AS_METADATA_PATH
from floresu_mcp.keys import JWKS_CHECK_NAME, RemoteKeyProvider, jwks_readiness_check
from tests.token_factory import ISSUER, JWKS_URI, make_fetch, new_key, public_jwks


async def test_discovers_metadata_then_jwks_and_caches() -> None:
    key = new_key(kid="kid-1")
    fetch = make_fetch(public_jwks(key))
    provider = RemoteKeyProvider(ISSUER, fetch)

    first = await provider.key_set_for("kid-1")
    second = await provider.key_set_for("kid-1")

    assert first.get_by_kid("kid-1") is not None
    # Two hops on the first load (metadata -> jwks), then served from cache: the
    # second lookup of a known kid triggers no further fetch.
    assert fetch.calls == [f"{ISSUER}{AS_METADATA_PATH}", JWKS_URI]  # type: ignore[attr-defined]
    assert second is first


async def test_unknown_kid_refetches_when_the_cooldown_has_elapsed() -> None:
    served = new_key(kid="kid-1")
    fetch = make_fetch(public_jwks(served))
    # Zero cooldown: an unknown kid always refetches (the rotation-pickup path).
    provider = RemoteKeyProvider(ISSUER, fetch, refresh_cooldown_seconds=0.0)

    await provider.key_set_for("kid-1")
    calls_after_load = len(fetch.calls)  # type: ignore[attr-defined]

    await provider.key_set_for("kid-unknown")

    # Exactly one extra discovery pass (metadata + jwks) to pick up a rotation.
    assert len(fetch.calls) == calls_after_load + 2  # type: ignore[attr-defined]


async def test_unknown_kid_is_throttled_within_the_cooldown_window() -> None:
    served = new_key(kid="kid-1")
    fetch = make_fetch(public_jwks(served))
    # A generous cooldown: the load itself counts as a refresh, so a burst of
    # unknown-kid lookups inside the window must NOT hammer the AS with refetches.
    provider = RemoteKeyProvider(ISSUER, fetch, refresh_cooldown_seconds=1000.0)

    await provider.key_set_for("kid-1")
    calls_after_load = len(fetch.calls)  # type: ignore[attr-defined]

    await provider.key_set_for("kid-unknown")
    await provider.key_set_for("kid-unknown")

    # No refetch: the DoS guard serves the cached set within the cooldown.
    assert len(fetch.calls) == calls_after_load  # type: ignore[attr-defined]


async def test_no_kid_is_served_from_cache_without_refetch() -> None:
    key = new_key(kid="kid-1")
    fetch = make_fetch(public_jwks(key))
    provider = RemoteKeyProvider(ISSUER, fetch)

    await provider.load()
    calls_after_load = len(fetch.calls)  # type: ignore[attr-defined]
    await provider.key_set_for(None)

    assert len(fetch.calls) == calls_after_load  # type: ignore[attr-defined]


async def test_readiness_ok_when_jwks_reachable() -> None:
    provider = RemoteKeyProvider(ISSUER, make_fetch(public_jwks(new_key())))
    check = jwks_readiness_check(provider)

    result = await check()

    assert result.name == JWKS_CHECK_NAME
    assert result.ok is True


async def test_readiness_degrades_when_discovery_fails() -> None:
    async def failing_fetch(_url: str) -> dict[str, object]:
        raise RuntimeError("AS unreachable")

    provider = RemoteKeyProvider(ISSUER, failing_fetch)
    check = jwks_readiness_check(provider)

    result = await check()

    assert result.ok is False
    assert result.detail is not None and "unreachable" in result.detail
