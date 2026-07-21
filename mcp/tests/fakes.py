"""In-memory test doubles for the RS boundary dependencies.

:class:`InMemoryRateLimitStore` stands in for Redis so the limiter's budget logic
tests without a live broker (a counter per key, no TTL semantics needed within a
single test). :func:`json_error` builds the backend's RFC 9457 problem+json body
the internal client maps through :func:`raise_for_problem`.
"""

from __future__ import annotations

from typing import Any

import httpx


class InMemoryRateLimitStore:
    """A :class:`~floresu_mcp.ratelimit.RateLimitStore` backed by a dict counter."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.windows: dict[str, int] = {}

    async def hit(self, key: str, window_seconds: int) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        # Record the window the first hit set, so a test can assert the TTL is
        # applied once (fixed window), mirroring the NX expiry in the real store.
        self.windows.setdefault(key, window_seconds)
        return self.counts[key]


def json_error(status: int, code: str, detail: str, **extra: Any) -> httpx.Response:
    """A backend RFC 9457 problem+json error response for the harness."""
    body = {
        "type": f"https://floresu.app/errors/{code.lower()}",
        "title": code,
        "status": status,
        "code": code,
        "detail": detail,
        **extra,
    }
    return httpx.Response(status, json=body, headers={"content-type": "application/problem+json"})
