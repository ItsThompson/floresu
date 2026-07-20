"""Unit tests for the redirect-URI allowlist (RFC 8252 loopback + exact https)."""

from __future__ import annotations

import pytest

from floresu.oauth.redirects import is_allowed_redirect, is_loopback


@pytest.mark.parametrize(
    "uri",
    [
        "http://127.0.0.1:8765/callback",
        "http://localhost:9000/cb",
        "http://[::1]:5000/cb",
    ],
)
def test_is_loopback_accepts_http_loopback_hosts(uri: str) -> None:
    assert is_loopback(uri) is True


@pytest.mark.parametrize(
    "uri",
    [
        "https://127.0.0.1/cb",  # https is not the loopback http case
        "http://evil.example.com/cb",
        "https://app.example.com/cb",
    ],
)
def test_is_loopback_rejects_non_http_loopback(uri: str) -> None:
    assert is_loopback(uri) is False


def test_exact_match_is_always_allowed() -> None:
    registered = ["https://app.example.com/callback"]
    assert is_allowed_redirect("https://app.example.com/callback", registered) is True


def test_loopback_matches_any_port_with_same_scheme_host_path() -> None:
    # RFC 8252: an agent binds a fresh ephemeral port each run, so the port varies
    # while scheme/host/path stay pinned to a registered loopback URI.
    registered = ["http://127.0.0.1:1/callback"]
    assert is_allowed_redirect("http://127.0.0.1:54321/callback", registered) is True


def test_loopback_path_mismatch_is_rejected() -> None:
    registered = ["http://127.0.0.1:1/callback"]
    assert is_allowed_redirect("http://127.0.0.1:54321/other", registered) is False


def test_non_loopback_non_exact_is_rejected() -> None:
    registered = ["https://app.example.com/callback"]
    assert is_allowed_redirect("https://evil.example.com/callback", registered) is False
