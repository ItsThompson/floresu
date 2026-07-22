"""Session/cookie config: secret validation and cookie attributes by environment."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import SecretStr

from floresu.accounts.config import (
    SessionConfig,
    build_cookie_config,
    build_session_config,
    validate_session_secret,
)
from floresu.core.settings import AppSettings

MakeSettings = Callable[..., AppSettings]

_STRONG_SECRET = "x" * 32


def test_dev_tolerates_a_weak_or_empty_secret() -> None:
    # Dev fail-safe denies via deny_all_sessions, so a short/empty secret must not
    # raise at startup (the app boots with auth unconfigured).
    validate_session_secret(SessionConfig(secret=SecretStr("")), is_dev=True)
    validate_session_secret(SessionConfig(secret=SecretStr("short")), is_dev=True)


def test_production_rejects_a_short_secret() -> None:
    with pytest.raises(RuntimeError, match="at least 32 bytes"):
        validate_session_secret(SessionConfig(secret=SecretStr("short")), is_dev=False)


def test_production_accepts_a_strong_secret() -> None:
    validate_session_secret(SessionConfig(secret=SecretStr(_STRONG_SECRET)), is_dev=False)


def test_cookie_is_insecure_and_host_only_in_dev(make_settings: MakeSettings) -> None:
    config = build_cookie_config(make_settings(environment="development", cookie_domain=""))
    assert config.secure is False
    assert config.domain is None
    assert config.samesite == "lax"


def test_cookie_is_secure_and_domain_pinned_in_prod(make_settings: MakeSettings) -> None:
    config = build_cookie_config(
        make_settings(environment="production", cookie_domain=".floresu.com")
    )
    assert config.secure is True
    assert config.domain == ".floresu.com"


def test_session_config_reads_the_settings_secret(make_settings: MakeSettings) -> None:
    config = build_session_config(make_settings(session_jwt_secret=SecretStr(_STRONG_SECRET)))
    assert config.secret.get_secret_value() == _STRONG_SECRET
